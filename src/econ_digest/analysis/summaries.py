"""Tier-specific article inputs and validated summary batches."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from ..config import Config
from ..models import Article, ArticleSummary, Classification, Issue
from ..taxonomy import TIER_ORDER
from .prompts import Unit, first_words, make_unit, numbered_text, prompt_json, split_units
from .validation import object_items, validate_summary

BATCH_LIMITS = {"A": 1, "B": 1, "C": 3, "D": 6, "E": 12}


def summary_payload(article: Article, classification: Classification, leader: Article | None) -> dict[str, Any]:
    tier = classification.tier
    payload: dict[str, Any] = {"article_id": article.id, "title": article.title, "rubric": article.rubric,
                               "section": article.section, "tier": tier, "taiwan_level": classification.taiwan_level,
                               "taiwan_link": classification.taiwan_link}
    if tier in {"A", "B", "C"}:
        payload["text"] = numbered_text(article.paragraphs)
    elif tier == "D":
        payload["text"] = first_words(article.paragraphs, 600) + "\n[末段] " + (
            article.paragraphs[-1] if article.paragraphs else "")
    else:
        payload["text"] = first_words(article.paragraphs, 250)
    if leader:
        payload["leader"] = {"article_id": leader.id, "title": leader.title,
                              "text": numbered_text(leader.paragraphs)}
    return payload


def summary_units(issue: Issue, classifications: dict[str, Classification], config: Config, *,
                  only_tier: str | None = None, limit: int | None = None) -> list[Unit]:
    by_id = {article.id: article for article in issue.articles}
    leaders = {classification.companion_id: by_id[classification.article_id]
               for classification in classifications.values() if classification.companion_id}
    selected = [article for article in issue.articles if classifications[article.id].tier in TIER_ORDER
                and (only_tier is None or classifications[article.id].tier == only_tier)]
    if limit is not None:
        selected = selected[:limit]
    units: list[Unit] = []
    for tier in TIER_ORDER:
        tier_articles = [article for article in selected if classifications[article.id].tier == tier]

        def build(batch: list[Article], current_tier: str = tier) -> Unit:
            ids = {article.id for article in batch}

            def validate(data: dict[str, Any]) -> None:
                for item in object_items(data, "articles", ids):
                    article = by_id[item["article_id"]]
                    validate_summary(item, article, current_tier, leader=article.id in leaders)

            return make_unit(f"summarize_{current_tier.lower()}", issue.issue_date, sorted(ids),
                             getattr(config.llm.models, f"summarize_{current_tier.lower()}"), validate,
                             tier=current_tier, articles=prompt_json([
                                 summary_payload(article, classifications[article.id], leaders.get(article.id))
                                 for article in batch]))

        units.extend(split_units(tier_articles, build, max_items=BATCH_LIMITS[tier], max_bytes=90_000))
    return units


def summary_model(item: dict[str, Any], tier: str, model: str) -> ArticleSummary:
    names = {field.name for field in fields(ArticleSummary)} - {"model", "tier"}
    return ArticleSummary.from_dict({**{key: value for key, value in item.items() if key in names},
                                     "tier": tier, "model": model})
