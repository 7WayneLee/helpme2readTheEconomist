"""Stage barriers, parallel analysis units, and the assembled digest."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Config
from ..fetch import issue_directory
from ..llm import GwgClient, LLMClient, LLMError, run_parallel
from ..models import ArticleSummary, Classification, Digest, EnglishPick, Issue, WeekBrief, save_json
from ..signals import find_taiwan_signals
from ..research.cna import CNAClient
from ..zhtw import lint_zh_tw, normalize_tree
from .brief import brief_unit
from .cache import SKIP_KEYS, UnitResult, UnitRunner, cache_focus_fallback
from .classification import apply_tiers, classify_units, fallback_classification, fixed_classification, pair_unit
from .english import guide_unit, pick_unit
from .editor import edit_digest
from .grounding import check_facts, ground_digest
from .focus import apply_focus, fallback_focus, focus_unit
from .prompts import Unit
from .summaries import summary_model, summary_units


class AnalysisError(Exception):
    """Too many failed analysis units for a report to be delivered."""


def make_llm_client(config: Config) -> LLMClient:
    return GwgClient(config.llm.gwg_bin, workdir=config.paths.data_dir / "agy-workdir",
                     call_timeout=config.llm.call_timeout_seconds,
                     no_account_wait=config.llm.no_account_wait_seconds)


def _parallel(runner: UnitRunner, units: list[Unit], config: Config) -> list[UnitResult]:
    results = run_parallel(runner.run, units, config.llm.max_parallel)
    collected: list[UnitResult] = []
    for result in results:
        if isinstance(result, BaseException):
            raise result
        collected.append(result)
    return collected


def _classification(item: dict[str, Any]) -> Classification:
    names = {field.name for field in fields(Classification)} - {"companion_id", "tier"}
    return Classification.from_dict({key: value for key, value in item.items() if key in names})


def _zh_strings(value: Any, key: str = "") -> list[str]:
    if key in SKIP_KEYS or key in {"paragraphs", "fly_title", "rubric", "date_published", "fetched_at", "generated_at"}:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for name, item in value.items() for text in _zh_strings(item, name)]
    if isinstance(value, list):
        return [text for item in value for text in _zh_strings(item)]
    return []


def analyze_issue(issue: Issue, config: Config, llm: LLMClient, *, workdir: Path,
                  english_history: list[dict] | None = None,
                  progress: Callable[[str], None] | None = None) -> Digest:
    return analyze_selected(issue, config, llm, workdir=workdir, english_history=english_history, progress=progress)


def analyze_selected(issue: Issue, config: Config, llm: LLMClient, *, workdir: Path,
                     english_history: list[dict] | None = None,
                     progress: Callable[[str], None] | None = None,
                     only_tier: str | None = None, limit: int | None = None) -> Digest:
    if len({article.id for article in issue.articles}) != len(issue.articles):
        raise AnalysisError("文章 id 重複，無法分析。")
    runner = UnitRunner(llm, workdir, progress, timeout_for=config.llm.timeout_for)
    by_id = {article.id: article for article in issue.articles}
    warnings: list[str] = []
    classifications: dict[str, Classification] = {}
    for article in issue.articles:
        fixed = fixed_classification(article)
        if fixed:
            classifications[article.id] = fixed
    for result in _parallel(runner, classify_units(issue, config), config):
        if result.data:
            for item in result.data["articles"]:
                classifications[item["article_id"]] = _classification(item)
        else:
            for identifier in result.unit.article_ids:
                classifications[identifier] = fallback_classification(by_id[identifier])
            warnings.append(f"分類失敗（{result.error_kind}）：{len(result.unit.article_ids)} 篇改用詞彙訊號與章節分類。")
    for identifier, classification in classifications.items():
        signals = find_taiwan_signals(by_id[identifier])
        if signals.mention_count >= 10 and classification.taiwan_level == 0:
            warnings.append(f"台灣訊號檢查：〈{by_id[identifier].title}〉強詞彙提及 {signals.mention_count} 次，但台灣等級為 0。")
    pairing = pair_unit(issue, config)
    if pairing:
        result = _parallel(runner, [pairing], config)[0]
        if result.data:
            for item in result.data["pairs"]:
                classifications[item["article_id"]].companion_id = item["companion_id"]
        else:
            warnings.append(f"經濟學人立場配對失敗（{result.error_kind}）：立場文章保留獨立摘要。")
    apply_tiers(issue.articles, classifications, config.tiers)
    base_tiers = {identifier: classification.tier for identifier, classification in classifications.items()}
    focus = focus_unit(issue, classifications, config)
    focus_ids: list[str] = []
    recovered_focus_failure = 0
    if focus:
        result = runner.run(focus)
        data = result.data
        if data is None:
            data = fallback_focus(issue, classifications, config.analysis.focus_count)
            cache_focus_fallback(workdir, result, data)
            recovered_focus_failure = 1
        if result.error_kind:
            warnings.append(f"本週焦點選文失敗（{result.error_kind}）：依封面對應文章、專題、立場對應文章與篇幅採用固定排序。")
        focus_ids = apply_focus(data, classifications)
    units = summary_units(issue, classifications, config, only_tier=only_tier, limit=limit, base_tiers=base_tiers)
    brief = brief_unit(issue, config)
    if brief:
        units.append(brief)
    pick = pick_unit(issue, classifications, config, english_history)
    summaries: dict[str, ArticleSummary] = {}
    week_brief: WeekBrief | None = None
    english: EnglishPick | None = None
    recovered_english_failure = 0

    class EnglishClient:
        error = ""

        def generate_json(self, *args: Any, **kwargs: Any) -> Any:
            try:
                return llm.generate_json(*args, **kwargs)
            except (LLMError, ValueError) as exc:
                self.error = str(exc)
                raise

    english_client = EnglishClient()
    english_runner = UnitRunner(english_client, workdir, progress, timeout_for=config.llm.timeout_for)

    def run_english(unit: Unit) -> tuple[UnitResult, str]:
        errors: list[str] = []
        english_client.error = ""

        def validate(data: dict[str, Any]) -> None:
            try:
                unit.validate(data)
            except ValueError as exc:
                errors.append(str(exc))
                raise

        result = english_runner.run(replace(unit, validate=validate))
        return result, english_client.error or (errors[-1] if errors else result.error_kind or "")

    def english_job(_: Unit) -> tuple[EnglishPick | None, str | None]:
        nonlocal recovered_english_failure
        assert pick is not None
        current_pick = pick
        failures: list[str] = []
        for attempt in range(2):
            selection, reason = run_english(current_pick)
            if not selection.data:
                failures.append(f"英文選文失敗（{selection.error_kind}）：{reason}")
                break
            article = by_id[selection.data["article_id"]]
            guide, reason = run_english(guide_unit(issue, article, config))
            if guide.data:
                names = {field.name for field in fields(EnglishPick)} - {"article_id", "reason_zh", "word_count", "reading_minutes"}
                data = {key: value for key, value in guide.data.items() if key in names}
                warning = None
                if failures:
                    recovered_english_failure = 1
                    warning = "；".join(failures) + "；已改選另一篇提供學習指南。"
                return EnglishPick.from_dict({**data, "article_id": article.id, "reason_zh": selection.data["reason_zh"],
                                              "word_count": article.word_count, "reading_minutes": math.ceil(article.word_count / 150)}), warning
            failures.append(f"英文學習指南失敗（{guide.error_kind}，文章 {article.id}）：{reason}")
            if attempt == 0:
                retry_pick = pick_unit(issue, classifications, config, english_history, exclude_ids=frozenset({article.id}))
                if retry_pick is None:
                    failures.append("沒有其他符合條件的英文選文")
                    break
                current_pick = retry_pick
        warning = "；".join(failures) + "；本期未提供學習指南。"
        logging.getLogger(__name__).warning("%s", warning)
        return None, warning

    def final_job(unit: Unit) -> UnitResult | tuple[EnglishPick | None, str | None]:
        return english_job(unit) if unit.stage == "english_pick" else runner.run(unit)

    jobs = units + ([pick] if pick else [])
    for result in run_parallel(final_job, jobs, config.llm.max_parallel):
        if isinstance(result, BaseException):
            raise result
        if isinstance(result, tuple):
            english, warning = result
            if warning:
                warnings.append(warning)
        elif result.unit.stage == "brief":
            if result.data:
                week_brief = WeekBrief.from_dict(result.data)
            else:
                warnings.append(f"本週要聞產生失敗（{result.error_kind}）。")
        elif result.data:
            for item in result.data["articles"]:
                summaries[item["article_id"]] = summary_model(item, result.unit.tier, result.model)
        else:
            for identifier in result.unit.article_ids:
                summaries[identifier] = ArticleSummary(identifier, result.unit.tier, "（摘要產生失敗）" + by_id[identifier].title)
            warnings.append(f"{result.unit.tier} 級摘要失敗（{result.error_kind}）：" + "、".join(result.unit.article_ids))
    if not pick:
        warnings.append("沒有符合篇幅與文章種類條件的英文選文。")
    edit_digest(issue, classifications, summaries, week_brief, config, runner, warnings)
    cna = CNAClient(config.paths.data_dir / "research", request_budget=config.research.cna_request_budget)
    ground_digest(issue, classifications, summaries, focus_ids, config, runner, cna, warnings)
    fact_alerts = check_facts(issue.issue_date, config, runner, cna, warnings)
    warnings.extend(cna.warnings)
    runner.total_units += english_runner.total_units
    runner.failed_units += english_runner.failed_units
    runner.stats.extend(english_runner.stats)
    failed_units = runner.failed_units - recovered_focus_failure - recovered_english_failure
    if runner.total_units and failed_units / runner.total_units > 0.30:
        raise AnalysisError(f"分析失敗比例超過 30%（{failed_units}/{runner.total_units}）；請稍後重試。")
    if only_tier is not None or limit is not None:
        warnings.append("本次僅執行指定範圍的摘要，供提示詞調整使用。")
    digest = Digest(issue.issue_date, datetime.now(timezone.utc).isoformat(), issue, classifications, summaries,
                    week_brief, english, sorted(runner.stats, key=lambda stat: (stat.stage, stat.model)), warnings,
                    focus_ids=focus_ids, fact_alerts=fact_alerts)
    # Source articles and diagnostic strings are not model-authored Chinese.
    digest = Digest.from_dict(normalize_tree(digest.to_dict(), skip_keys=SKIP_KEYS | {"issue", "warnings", "llm_calls"}))
    findings = [finding for value in _zh_strings(digest.to_dict()) for finding in lint_zh_tw(value)]
    digest.warnings = list(dict.fromkeys([*warnings, *findings]))
    output = issue_directory(config, issue.issue_date) / ("digest-tuning.json" if only_tier is not None or limit is not None else "digest.json")
    save_json(output, digest)
    return digest
