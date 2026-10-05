"""Select the week's international focus after pairing and depth assignment."""

from __future__ import annotations

import re
from typing import Any

from ..config import Config
from ..models import Article, Classification, Issue
from ..taxonomy import TIER_ORDER
from .prompts import Unit, make_unit, prompt_json
from .validation import chinese_length, text

EXCLUDED_KINDS = {"letters", "obituary", "cartoon", "indicators", "world_politics", "world_business"}


def focus_candidates(issue: Issue, classifications: dict[str, Classification]) -> list[Article]:
    return [article for article in issue.articles
            if classifications[article.id].taiwan_level == 0
            and classifications[article.id].tier in TIER_ORDER and article.kind not in EXCLUDED_KINDS]


def companion_ids(issue: Issue, classifications: dict[str, Classification]) -> tuple[set[str], set[str]]:
    cover: set[str] = set()
    leaders: set[str] = set()
    for article in issue.articles:
        companion = classifications[article.id].companion_id
        if article.kind == "leader" and companion:
            leaders.add(companion)
            if article.is_cover:
                cover.add(companion)
    return cover, leaders


def validate_focus(data: dict[str, Any], ids: set[str], count: int) -> None:
    items = data.get("focus")
    if not isinstance(items, list) or len(items) != min(count, len(ids)):
        raise ValueError(f"focus 必須恰好包含 {min(count, len(ids))} 篇文章")
    used: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("focus 必須是物件陣列")
        identifier = item.get("article_id")
        if not isinstance(identifier, str) or identifier not in ids or identifier in used:
            raise ValueError("focus article_id 必須是未重複的候選文章 id")
        reason = text(item.get("reason"), "focus.reason")
        if not chinese_length(reason) or len(re.findall(r"[。！？]", reason)) > 1:
            raise ValueError("focus.reason 必須是一句正體中文")
        used.add(identifier)


def focus_unit(issue: Issue, classifications: dict[str, Classification], config: Config) -> Unit | None:
    candidates = focus_candidates(issue, classifications)
    if not candidates:
        return None
    ids = {article.id for article in candidates}
    cover, leaders = companion_ids(issue, classifications)
    return make_unit("focus", issue.issue_date, sorted(ids), config.llm.models.focus,
                     lambda data: validate_focus(data, ids, config.analysis.focus_count),
                     count=min(config.analysis.focus_count, len(candidates)), candidates=prompt_json([
                         {"id": article.id, "section": article.section, "kind": article.kind,
                          "fly_title": article.fly_title, "title": article.title, "rubric": article.rubric,
                          "title_zh": classifications[article.id].title_zh,
                          "category": classifications[article.id].category, "tier": classifications[article.id].tier,
                          "word_count": article.word_count, "is_cover_companion": article.id in cover,
                          "has_merged_leader": article.id in leaders} for article in candidates]))


def fallback_focus(issue: Issue, classifications: dict[str, Classification], count: int) -> dict[str, Any]:
    cover, leaders = companion_ids(issue, classifications)

    def priority(article: Article) -> tuple[int, int, int, str]:
        rank = (0 if article.id in cover else 1 if article.kind == "briefing" else
                2 if article.id in leaders else 3 if classifications[article.id].tier == "C" else 4)
        return rank, -article.word_count, article.order, article.id

    reasons = ["封面報導的對應文章，優先列為本週深度解析。", "本期專題，優先深入理解議題脈絡。",
               "包含經濟學人立場，優先理解報導與作者主張。", "篇幅較長的 C 級報導，優先深入分析。",
               "依文章篇幅與原始順序，補足本週深度解析。"]
    selected = sorted(focus_candidates(issue, classifications), key=priority)[:count]
    return {"focus": [{"article_id": article.id, "reason": reasons[priority(article)[0]]} for article in selected]}


def apply_focus(data: dict[str, Any], classifications: dict[str, Classification]) -> list[str]:
    ids = [item["article_id"] for item in data["focus"]]
    for identifier in ids:
        classifications[identifier].tier = "A"
    return ids
