"""Read-only call estimates using cached decisions where available."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import Config
from ..models import Classification, Issue
from .brief import brief_unit
from .cache import read_cache
from .classification import apply_tiers, classify_units, fallback_classification, fixed_classification, pair_unit
from .english import english_candidates, guide_unit, pick_unit
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
    units.extend(summary_units(issue, classifications, config, only_tier=only_tier, limit=limit))
    brief = brief_unit(issue, config)
    if brief:
        units.append(brief)
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
    return units, estimated
