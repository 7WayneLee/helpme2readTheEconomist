"""Evidence-backed Taiwan statements and weekly fact-sheet freshness alerts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..config import Config
from ..facts import load_taiwan_facts
from ..models import ArticleSummary, Classification, Issue, Source, save_json
from ..research.cna import CNAClient, Evidence, cna_url
from ..signals import find_taiwan_signals
from ..taxonomy import assign_tier
from .cache import UnitRunner
from .prompts import Unit, make_unit, prompt_json, split_units
from .validation import chinese_length, object_items

FACT_QUERIES = ("台灣 邦交國", "行政院長", "立法院 席次", "國防預算", "台灣 對中出口", "台積電 海外廠")


def validate_queries(data: dict[str, Any], ids: set[str]) -> None:
    for item in object_items(data, "articles", ids):
        queries = item.get("queries")
        if (not isinstance(queries, list) or not 1 <= len(queries) <= 3
                or any(not isinstance(query, str) or not query.strip() or len(query) > 20
                       or not chinese_length(query) for query in queries)):
            raise ValueError("ground queries: 1–3 nonempty Chinese queries of at most 20 characters")


def query_units(issue: Issue, ids: list[str], classifications: dict[str, Classification],
                summaries: dict[str, ArticleSummary], config: Config) -> list[Unit]:
    by_id = {article.id: article for article in issue.articles}

    def build(batch: list[str]) -> Unit:
        return make_unit("ground_queries", issue.issue_date, batch, config.llm.models.ground,
                         lambda data: validate_queries(data, set(batch)), articles=prompt_json([
                             {"article_id": identifier, "title": by_id[identifier].title,
                              "rubric": by_id[identifier].rubric,
                              "title_zh": classifications[identifier].title_zh,
                              "headline_zh": summaries[identifier].headline_zh if identifier in summaries else ""}
                             for identifier in batch]))

    return split_units(ids, build, max_items=10000, max_bytes=60_000)


def _statement(value: Any, evidence_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    text, basis = value.get("text_zh"), value.get("basis")
    if (not isinstance(text, str) or not text.strip() or "社論" in text
            or not isinstance(basis, list) or not basis
            or any(not isinstance(item, str) or item not in evidence_ids | {"article", "facts"} for item in basis)):
        return None
    return {"text_zh": text.strip(), "basis": list(dict.fromkeys(basis))}


def validate_grounding(data: dict[str, Any], evidence: dict[str, list[Evidence]]) -> None:
    for item in object_items(data, "articles", set(evidence)):
        level = item.get("taiwan_level")
        if type(level) is not int or level not in {0, 1, 2, 3}:
            raise ValueError("ground taiwan_level must be 0–3")
        available = {entry.id for entry in evidence[item["article_id"]]}
        link = _statement(item.get("taiwan_link"), available)
        implications = item.get("taiwan_implications", [])
        if not isinstance(implications, list):
            raise ValueError("ground implications must be an array")
        item["taiwan_implications"] = [kept for value in implications
                                       if (kept := _statement(value, available))][:3]
        # Unsupported statements cannot leave a nonzero classification behind.
        item["taiwan_link"] = link if level else None
        if level and link is None:
            item["taiwan_level"] = 0


def grounding_units(issue: Issue, ids: list[str], classifications: dict[str, Classification],
                    summaries: dict[str, ArticleSummary], evidence: dict[str, list[Evidence]],
                    config: Config) -> list[Unit]:
    by_id = {article.id: article for article in issue.articles}

    def build(batch: list[str]) -> Unit:
        payload = []
        for identifier in batch:
            article = by_id[identifier]
            summary = summaries.get(identifier)
            chinese = ({key: value for key, value in asdict(summary).items()
                        if key in {"headline_zh", "summary_zh", "key_points", "background", "argument"}}
                       if summary else {})
            payload.append({"article_id": identifier, "title": article.title, "rubric": article.rubric,
                            "provisional_taiwan_level": classifications[identifier].taiwan_level,
                            "chinese_summary": chinese, "signals": find_taiwan_signals(article).snippets,
                            "evidence": [entry.to_dict() for entry in evidence[identifier]]})
        selected = {identifier: evidence[identifier] for identifier in batch}
        return make_unit("ground", issue.issue_date, batch, config.llm.models.ground,
                         lambda data: validate_grounding(data, selected), facts=load_taiwan_facts(),
                         articles=prompt_json(payload))

    return split_units(ids, build, max_items=3, max_bytes=90_000)


def _sources(statements: list[dict[str, Any]], evidence: list[Evidence]) -> list[Source]:
    used = {identifier for statement in statements for identifier in statement["basis"]}
    return [entry.source for entry in evidence if entry.id in used]


def apply_grounding(data: dict[str, Any], issue: Issue, classifications: dict[str, Classification],
                    summaries: dict[str, ArticleSummary], evidence: dict[str, list[Evidence]], config: Config,
                    focus_ids: list[str]) -> None:
    by_id = {article.id: article for article in issue.articles}
    validate_grounding(data, evidence)
    for item in data["articles"]:
        identifier = item["article_id"]
        classification = classifications[identifier]
        classification.taiwan_level = item["taiwan_level"]
        link = item["taiwan_link"]
        classification.taiwan_link = link["text_zh"] if link else None
        classification.sources = _sources([link] if link else [], evidence[identifier])
        classification.tier = assign_tier(by_id[identifier].kind, classification.taiwan_level,
                                           classification.category, classification.companion_id is not None, config.tiers)
        if identifier in focus_ids:
            classification.tier = "A"
        if identifier in summaries:
            summary = summaries[identifier]
            # Keep the completed summary's depth when the display section changes.
            summary.taiwan_implications = [entry["text_zh"] for entry in item["taiwan_implications"]]
            summary.sources = _sources(item["taiwan_implications"], evidence[identifier])


def ground_digest(issue: Issue, classifications: dict[str, Classification], summaries: dict[str, ArticleSummary],
                  focus_ids: list[str], config: Config, runner: UnitRunner, cna: CNAClient,
                  warnings: list[str]) -> None:
    ids = [article.id for article in issue.articles if classifications[article.id].taiwan_level >= 1
           or article.id in focus_ids]
    if not ids:
        return
    queries: dict[str, list[str]] = {}
    for unit in query_units(issue, ids, classifications, summaries, config):
        result = runner.run(unit)
        if result.data:
            queries.update({item["article_id"]: item["queries"] for item in result.data["articles"]})
        else:
            warnings.append("台灣關聯搜尋詞產生失敗，改用原文與事實檔查證。")
    previous_errors = len(cna.errors)
    evidence = {identifier: cna.retrieve(queries[identifier]) if identifier in queries else [] for identifier in ids}
    if len(cna.errors) > previous_errors:
        warnings.append("中央社暫時無法連線；台灣關聯改以原文、事實檔與已取得的證據查證。")
    for unit in grounding_units(issue, ids, classifications, summaries, evidence, config):
        result = runner.run(unit)
        selected = {identifier: evidence[identifier] for identifier in unit.article_ids}
        if result.data:
            apply_grounding(result.data, issue, classifications, summaries, selected, config, focus_ids)
        else:
            # Provisional links must not masquerade as verified statements.
            empty = {"articles": [{"article_id": identifier, "taiwan_level": 0,
                                     "taiwan_link": None, "taiwan_implications": []}
                                    for identifier in unit.article_ids]}
            apply_grounding(empty, issue, classifications, summaries, selected, config, focus_ids)
            warnings.append("台灣關聯查證失敗，暫不列入台灣專區，保留原摘要。")


def validate_fact_alerts(data: dict[str, Any], urls: set[str]) -> None:
    if not isinstance(data.get("alerts"), list):
        raise ValueError("facts alerts must be an array")
    data["alerts"] = [item for item in data["alerts"] if isinstance(item, dict)
                      and all(isinstance(item.get(key), str) and item[key].strip()
                              for key in ("fact", "suspected_new_value", "evidence_url"))
                      and item["evidence_url"] in urls and cna_url(item["evidence_url"])]


def facts_unit(issue_date: str, evidence: list[Evidence], config: Config) -> Unit:
    urls = {entry.source.url for entry in evidence}
    unit = make_unit("facts", issue_date, [], config.llm.models.facts,
                     lambda data: validate_fact_alerts(data, urls), facts=load_taiwan_facts(),
                     evidence=prompt_json([entry.to_dict() for entry in evidence]))
    if unit.prompt_bytes > 90_000:
        raise ValueError("facts exceeds 90,000 prompt bytes")
    return unit


def check_facts(issue_date: str, config: Config, runner: UnitRunner, cna: CNAClient,
                warnings: list[str]) -> list[dict]:
    # A successful check is fixed for this issue, even when the search cache ages.
    identity = hashlib.sha256((load_taiwan_facts() + prompt_json(config.llm.models.facts)).encode()).hexdigest()
    path = runner.workdir / f"facts-check-{issue_date}.json"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(saved, dict) and saved.get("identity") == identity and isinstance(saved.get("alerts"), list):
            validate_fact_alerts(saved, set(saved.get("urls", [])))
            warnings.extend(saved.get("warnings", []))
            return saved["alerts"]
    except (OSError, ValueError, TypeError):
        pass
    before = len(cna.errors)
    evidence = cna.retrieve(list(FACT_QUERIES))
    notices = (["中央社暫時無法連線；台灣事實檔更新檢查僅能使用已取得的證據。"]
               if len(cna.errors) > before else [])
    warnings.extend(notices)
    result = runner.run(facts_unit(issue_date, evidence, config))
    if not result.data:
        warnings.append("台灣事實檔更新檢查失敗，請稍後重試。")
        return []
    save_json(path, {"identity": identity, "alerts": result.data["alerts"],
                     "urls": [entry.source.url for entry in evidence], "warnings": notices})
    return result.data["alerts"]
