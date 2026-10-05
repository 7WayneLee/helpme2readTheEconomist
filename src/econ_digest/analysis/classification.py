"""Classification context, leader pairing, and the final depth policy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..config import Config, TiersConfig
from ..models import Article, Classification, Issue
from ..signals import find_taiwan_signals
from ..taxonomy import CATEGORIES, TAIWAN_LEVELS, TAIWAN_LEVEL_DEFINITIONS, TIER_ORDER, assign_tier
from .prompts import Unit, first_words, make_unit, prompt_json, split_units
from .validation import object_items, text

FIXED_TITLES = {"cartoon": "漫畫", "indicators": "經濟與金融指標",
                "world_politics": "本週政治要聞", "world_business": "本週商業要聞"}
SECTION_CATEGORIES = {"united states": "intl.us", "china": "intl.china", "asia": "intl.asia",
                      "europe": "intl.europe", "britain": "intl.europe", "business": "finance",
                      "finance & economics": "finance", "science & technology": "science",
                      "culture": "culture", "obituary": "culture"}


def fallback_classification(article: Article) -> Classification:
    signals = find_taiwan_signals(article)
    level = 3 if signals.strong_terms else 0
    return Classification(article.id, level, bool(signals.strong_terms),
                          "文中提及「" + "、".join(signals.strong_terms) + "」，台灣關聯待確認。" if level else None,
                          SECTION_CATEGORIES.get(article.section.casefold(), "intl.other"), article.title)


def fixed_classification(article: Article) -> Classification | None:
    if article.kind not in FIXED_TITLES:
        return None
    return Classification(article.id, 0, False, None, "intl.other", FIXED_TITLES[article.kind],
                          tier="skip" if article.kind in {"cartoon", "indicators"} else "brief")


def classification_payload(article: Article) -> dict[str, Any]:
    signals = find_taiwan_signals(article)
    return {"id": article.id, "section": article.section, "fly_title": article.fly_title,
            "kind": article.kind, "title": article.title, "rubric": article.rubric,
            "opening": first_words(article.paragraphs, 150),
            "strong_terms": signals.strong_terms, "weak_terms": signals.weak_terms,
            "snippets": signals.snippets[:5]}


def validate_classification(data: dict[str, Any], ids: set[str]) -> None:
    for item in object_items(data, "articles", ids):
        level = item.get("taiwan_level")
        if type(level) is not int or level not in {0, 1, 2, 3}:
            raise ValueError("taiwan_level must be 0, 1, 2, or 3")
        if type(item.get("mentions_taiwan")) is not bool:
            raise ValueError("mentions_taiwan must be a boolean")
        if not isinstance(item.get("category"), str) or item["category"] not in CATEGORIES:
            raise ValueError("category must be a CATEGORIES key")
        text(item.get("title_zh"), "title_zh")
        if level >= 1:
            text(item.get("taiwan_link"), "taiwan_link (required for level >= 1)")
        elif item.get("taiwan_link") is not None and not isinstance(item.get("taiwan_link"), str):
            raise ValueError("taiwan_link must be a string or null")


def classify_units(issue: Issue, config: Config) -> list[Unit]:
    articles = [article for article in issue.articles if article.kind not in FIXED_TITLES]

    def build(batch: list[Article]) -> Unit:
        ids = {article.id for article in batch}
        return make_unit("classify", issue.issue_date, sorted(ids), config.llm.models.classify,
                         lambda data: validate_classification(data, ids),
                         levels=prompt_json({0: "無實質台灣關聯", **{
                             level: TAIWAN_LEVELS[level] + "：" + definition
                             for level, definition in TAIWAN_LEVEL_DEFINITIONS.items()}}),
                         categories=prompt_json(CATEGORIES), articles=prompt_json([
                             classification_payload(article) for article in batch]))

    return split_units(articles, build, max_items=20, max_bytes=60_000)


def validate_pairs(data: dict[str, Any], leaders: set[str], candidates: set[str]) -> None:
    used: set[str] = set()
    for item in object_items(data, "pairs", leaders):
        if "companion_id" not in item:
            raise ValueError("Every pair requires companion_id or null")
        companion = item["companion_id"]
        if companion is not None:
            if not isinstance(companion, str) or companion not in candidates or companion in used:
                raise ValueError("companion_id must be an unused non-leader candidate id")
            used.add(companion)


def pair_unit(issue: Issue, config: Config) -> Unit | None:
    leaders = [article for article in issue.articles if article.kind == "leader"]
    candidates = [article for article in issue.articles if article.kind != "leader" and article.kind not in FIXED_TITLES]
    if not leaders or not candidates:
        return None
    leader_ids = {article.id for article in leaders}
    candidate_ids = {article.id for article in candidates}
    unit = make_unit("pair", issue.issue_date, sorted(leader_ids | candidate_ids), config.llm.models.pair,
                     lambda data: validate_pairs(data, leader_ids, candidate_ids),
                     leaders=prompt_json([{"id": article.id, "title": article.title, "rubric": article.rubric,
                                           "opening": first_words(article.paragraphs, 80)} for article in leaders]),
                     candidates=prompt_json([{"id": article.id, "section": article.section,
                                              "title": article.title, "rubric": article.rubric} for article in candidates]))
    if unit.prompt_bytes > 90_000:
        raise ValueError("pair exceeds 90,000 prompt bytes")
    return unit


def apply_tiers(articles: Sequence[Article], classifications: dict[str, Classification], tiers: TiersConfig) -> None:
    for article in articles:
        classification = classifications[article.id]
        classification.tier = assign_tier(article.kind, classification.taiwan_level, classification.category,
                                          classification.companion_id is not None, tiers)
    for article in articles:
        companion = classifications[article.id].companion_id
        if article.kind == "leader" and companion:
            minimum = tiers.cover_companion_min if article.is_cover else tiers.leader_companion_min
            classification = classifications[companion]
            if classification.tier in TIER_ORDER and TIER_ORDER.index(minimum) < TIER_ORDER.index(classification.tier):
                classification.tier = minimum
