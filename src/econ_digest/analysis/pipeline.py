"""Stage barriers, parallel analysis units, and the assembled digest."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Config
from ..fetch import issue_directory
from ..llm import GwgClient, LLMClient, run_parallel
from ..models import ArticleSummary, Classification, Digest, EnglishPick, Issue, WeekBrief, save_json
from ..signals import find_taiwan_signals
from ..zhtw import lint_zh_tw
from .brief import brief_unit
from .cache import SKIP_KEYS, UnitResult, UnitRunner
from .classification import apply_tiers, classify_units, fallback_classification, fixed_classification, pair_unit
from .english import guide_unit, pick_unit
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
    runner = UnitRunner(llm, workdir, progress)
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
            warnings.append(f"社論配對失敗（{result.error_kind}）：社論保留獨立摘要。")
    apply_tiers(issue.articles, classifications, config.tiers)
    units = summary_units(issue, classifications, config, only_tier=only_tier, limit=limit)
    brief = brief_unit(issue, config)
    if brief:
        units.append(brief)
    pick = pick_unit(issue, classifications, config, english_history)
    summaries: dict[str, ArticleSummary] = {}
    week_brief: WeekBrief | None = None
    english: EnglishPick | None = None

    def english_job(_: Unit) -> tuple[EnglishPick | None, str | None]:
        assert pick is not None
        selection = runner.run(pick)
        if not selection.data:
            return None, f"英文選文失敗（{selection.error_kind}），本期未提供學習指南。"
        article = by_id[selection.data["article_id"]]
        guide = runner.run(guide_unit(issue, article, config))
        if not guide.data:
            return None, f"英文學習指南失敗（{guide.error_kind}），本期未提供學習指南。"
        names = {field.name for field in fields(EnglishPick)} - {"article_id", "reason_zh", "word_count", "reading_minutes"}
        data = {key: value for key, value in guide.data.items() if key in names}
        return EnglishPick.from_dict({**data, "article_id": article.id, "reason_zh": selection.data["reason_zh"],
                                      "word_count": article.word_count, "reading_minutes": math.ceil(article.word_count / 150)}), None

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
    if runner.total_units and runner.failed_units / runner.total_units > 0.30:
        raise AnalysisError(f"分析失敗比例超過 30%（{runner.failed_units}/{runner.total_units}）；請稍後重試。")
    if only_tier is not None or limit is not None:
        warnings.append("本次僅執行指定範圍的摘要，供提示詞調整使用。")
    digest = Digest(issue.issue_date, datetime.now(timezone.utc).isoformat(), issue, classifications, summaries,
                    week_brief, english, sorted(runner.stats, key=lambda stat: (stat.stage, stat.model)), warnings)
    findings = [finding for value in _zh_strings(digest.to_dict()) for finding in lint_zh_tw(value)]
    digest.warnings = list(dict.fromkeys([*warnings, *findings]))
    output = issue_directory(config, issue.issue_date) / ("digest-tuning.json" if only_tier is not None or limit is not None else "digest.json")
    save_json(output, digest)
    return digest
