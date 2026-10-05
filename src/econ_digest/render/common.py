"""Shared report ordering and plain-text presentation fields."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..models import Article, ArticleSummary, BriefItem, Classification, Digest
from ..taxonomy import CATEGORIES, CATEGORY_SHORT_LABELS, TAIWAN_LEVELS, TIER_ORDER

TAIWAN_TAG = "【台灣相關】"


def ordered_brief(items: list[BriefItem]) -> list[BriefItem]:
    return sorted(items, key=lambda item: not item.taiwan_related)


@dataclass(frozen=True)
class Entry:
    article: Article
    classification: Classification
    summary: ArticleSummary


@dataclass(frozen=True)
class Section:
    anchor: str
    title: str
    entries: list[Entry]


def title(digest: Digest) -> str:
    date = datetime.strptime(digest.issue_date, "%Y.%m.%d")
    return f"經濟學人導讀｜{date.year} 年 {date.month} 月 {date.day} 日號"


def generation_time(digest: Digest) -> str:
    stamp = datetime.fromisoformat(digest.generated_at.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=ZoneInfo("UTC"))
    return stamp.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M（台北時間）")


def entries(digest: Digest) -> list[Entry]:
    result = []
    for article in digest.issue.articles:
        classification = digest.classifications.get(article.id)
        summary = digest.summaries.get(article.id)
        if classification is not None and summary is not None and summary.tier in TIER_ORDER:
            result.append(Entry(article, classification, summary))
    return sorted(result, key=lambda item: (TIER_ORDER.index(item.summary.tier), item.article.order))


def sections(digest: Digest) -> list[Section]:
    selected = entries(digest)
    result = [Section(f"taiwan-{level}", f"{'一二三'[level - 1]}、{label}", [
        item for item in selected if item.classification.taiwan_level == level
    ]) for level, label in TAIWAN_LEVELS.items()]
    result.extend(Section(category.replace(".", "-"), CATEGORY_SHORT_LABELS[category], items)
                  for category in CATEGORIES
                  if (items := [item for item in selected if item.classification.taiwan_level == 0
                                and item.classification.category == category]))
    return result


def english_article(digest: Digest) -> Article | None:
    if digest.english is None:
        return None
    return next((article for article in digest.issue.articles if article.id == digest.english.article_id), None)


def overview(digest: Digest) -> str:
    selected = entries(digest)
    counts = [sum(item.classification.taiwan_level == level for item in selected) for level in (1, 2, 3)]
    pick = english_article(digest)
    return (f"共 {len(digest.issue.articles)} 篇文章｜台灣 T1 {counts[0]} 篇、T2 {counts[1]} 篇、"
            f"T3 {counts[2]} 篇｜英文選文：{pick.title if pick else '本期未選文'}")


def word_count_label(count: int) -> str:
    return f"英文 {count:,} 字"


def metadata(entry: Entry) -> str:
    article = entry.article
    tags = {"leader": "社論", "column": "專欄", "briefing": "特別報導"}
    parts = [article.section]
    if article.fly_title:
        parts.append(article.fly_title)
    parts.append(word_count_label(article.word_count))
    if article.kind in tags:
        parts.append(tags[article.kind])
    if article.is_cover:
        parts.append("封面故事")
    return " · ".join(parts)


def summary_fields(summary: ArticleSummary, *, headline: bool = True) -> list[tuple[str, list[str]]]:
    fields: list[tuple[str, list[str]]] = []
    if headline:
        fields.append(("一句話重點", [summary.headline_zh]))
    for label, value in (("背景", summary.background), ("文章脈絡", summary.structure)):
        if value:
            fields.append((label, value if isinstance(value, list) else [value]))
    if summary.argument:
        argument = summary.argument
        fields.append(("論證", [f"主張：{argument.claim}", *[f"證據：{v}" for v in argument.evidence],
                                *[f"反方觀點：{v}" for v in argument.counterpoints], f"結論：{argument.conclusion}"]))
    if summary.key_data:
        fields.append(("關鍵數據", summary.key_data))
    if summary.quotes:
        fields.append(("重要引述", [f"{quote.en}\n中譯：{quote.zh}" for quote in summary.quotes]))
    for label, value in (("經濟學人的立場與盲點", summary.stance),
                         ("對台灣的意涵", summary.taiwan_implications),
                         ("延伸思考", summary.further_questions),
                         ("重點", summary.key_points), ("摘要", summary.summary_zh)):
        if value:
            fields.append((label, value if isinstance(value, list) else [value]))
    return fields


def merged_leader_titles(digest: Digest, entry: Entry) -> list[str]:
    return [article.title for article in digest.issue.articles
            if article.kind == "leader" and article.id != entry.article.id
            and (classification := digest.classifications.get(article.id)) is not None
            and (classification.companion_id == entry.article.id
                 or entry.classification.companion_id == article.id)]


def skipped(digest: Digest) -> list[tuple[str, str]]:
    return [(article.title, "漫畫" if article.kind == "cartoon" else "經濟指標" if article.kind == "indicators" else "略過")
            for article in digest.issue.articles
            if article.kind in ("cartoon", "indicators")
            or (classification := digest.classifications.get(article.id)) is not None and classification.tier == "skip"]


def statistics(digest: Digest) -> list[str]:
    stages: dict[str, float] = {}
    for call in digest.llm_calls:
        stages[call.stage] = stages.get(call.stage, 0.0) + call.duration_seconds
    return [f"LLM 呼叫：{len(digest.llm_calls)} 次（成功 {sum(call.ok for call in digest.llm_calls)} 次）",
            f"Token：{sum(call.total_tokens for call in digest.llm_calls):,}",
            *[f"{stage}：{seconds:.1f} 秒" for stage, seconds in stages.items()],
            "使用模型：" + ("、".join(dict.fromkeys(call.model for call in digest.llm_calls)) or "無")]
