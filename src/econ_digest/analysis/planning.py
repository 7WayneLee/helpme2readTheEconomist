"""Read-only call estimates using cached decisions where available."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import Config
from ..models import ArticleSummary, Classification, Issue, WeekBrief
from .brief import brief_unit
from .cache import read_cache
from .classification import apply_tiers, classify_units, fallback_classification, fixed_classification, pair_unit
from .english import english_candidates, guide_unit, pick_unit
from .focus import apply_focus, fallback_focus, focus_unit
from .editor import edit_units
from .grounding import facts_unit, grounding_units, query_units
from .prompts import Unit
from .summaries import summary_units


def plan_issue(issue: Issue, config: Config, *, workdir: Path,
               english_history: list[dict[str, Any]] | None = None,
               only_tier: str | None = None, limit: int | None = None) -> tuple[list[Unit], bool]:
    by_id = {article.id: article for article in issue.articles}
    classifications = {article.id: fixed_classification(article) or fallback_classification(article)
                       for article in issue.articles}
    units = classify_units(issue, config)
    estimated = False
    for unit in units:
        cached = read_cache(workdir, unit)
        if cached and cached.data:
            for item in cached.data["articles"]:
                classifications[item["article_id"]] = Classification.from_dict(item)
        else:
            estimated = True
    pairing = pair_unit(issue, config)
    if pairing:
        units.append(pairing)
        cached = read_cache(workdir, pairing)
        if cached and cached.data:
            for item in cached.data["pairs"]:
                classifications[item["article_id"]].companion_id = item["companion_id"]
        else:
            estimated = True
    apply_tiers(issue.articles, classifications, config.tiers)
    base_tiers = {identifier: classification.tier for identifier, classification in classifications.items()}
    focus = focus_unit(issue, classifications, config)
    focus_ids: list[str] = []
    if focus:
        units.append(focus)
        cached = read_cache(workdir, focus)
        if cached and cached.data:
            focus_ids = apply_focus(cached.data, classifications)
        else:
            estimated = True
            focus_ids = apply_focus(fallback_focus(issue, classifications, config.analysis.focus_count), classifications)
    summary_calls = summary_units(issue, classifications, config, only_tier=only_tier, limit=limit, base_tiers=base_tiers)
    units.extend(summary_calls)
    summaries = {}
    for unit in summary_calls:
        cached = read_cache(workdir, unit)
        if cached and cached.data:
            summaries.update({item["article_id"]: ArticleSummary.from_dict({**item, "tier": unit.tier})
                              for item in cached.data["articles"]})
        else:
            summaries.update({identifier: ArticleSummary(identifier, unit.tier, "摘要尚待產生")
                              for identifier in unit.article_ids})
    brief = brief_unit(issue, config)
    if brief:
        units.append(brief)
    cached_brief = read_cache(workdir, brief) if brief else None
    week_brief = WeekBrief.from_dict(cached_brief.data) if cached_brief and cached_brief.data else None
    pick = pick_unit(issue, classifications, config, english_history)
    if pick:
        units.append(pick)
        cached = read_cache(workdir, pick)
        if cached and cached.data:
            article = by_id[cached.data["article_id"]]
        else:
            estimated = True
            article = max(english_candidates(issue, config), key=lambda candidate: len("\n".join(candidate.paragraphs).encode()))
        units.append(guide_unit(issue, article, config))
    units.extend(edit_units(issue, classifications, summaries, week_brief, config))
    ground_ids = [article.id for article in issue.articles if classifications[article.id].taiwan_level >= 1
                  or article.id in focus_ids]
    units.extend(query_units(issue, ground_ids, classifications, summaries, config))
    # Evidence is deliberately absent from read-only plans; retrieval never runs here.
    units.extend(grounding_units(issue, ground_ids, classifications, summaries,
                                  {identifier: [] for identifier in ground_ids}, config))
    units.append(facts_unit(issue.issue_date, [], config))
    return units, estimated
