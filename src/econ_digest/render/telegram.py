"""Compact Telegram HTML with expandable details and safe message boundaries."""

from __future__ import annotations

from ..models import BriefItem, Digest
from ..telegram.format import blockquote, bold, escape, italic, pack_blocks, split_html
from .common import (Entry, english_article, merged_leader_titles, metadata, overview,
                     sections, summary_fields, title)


def field(label: str, values: list[str]) -> str:
    return bold(label) + "\n" + "\n".join(("• " if len(values) > 1 else "") + escape(value) for value in values)


def brief_list(items: list[BriefItem]) -> str:
    return "\n".join(("🇹🇼 " if item.taiwan_related else "• ") + escape(item.text_zh) for item in items)


def overview_html(digest: Digest) -> str:
    lines = ["📰 " + bold(title(digest)), escape(overview(digest)), "", bold("本週要聞速覽")]
    if digest.week_brief:
        brief = digest.week_brief
        taiwan = [item for item in [*brief.politics, *brief.business] if item.taiwan_related]
        if taiwan:
            lines.append(brief_list(taiwan))
        lines.extend([bold("政治"), brief_list([item for item in brief.politics if not item.taiwan_related][:8]),
                      bold("商業"), brief_list([item for item in brief.business if not item.taiwan_related][:5])])
        lines.append(blockquote(bold("完整政治要聞") + "\n" + brief_list(brief.politics) + "\n\n"
                                + bold("完整商業要聞") + "\n" + brief_list(brief.business), expandable=True))
    pick = english_article(digest)
    lines.extend(["", bold("英文學習選文"), italic(pick.title) if pick else "本期未選文。"])
    return "\n".join(lines)


def full_taiwan_html(digest: Digest, entry: Entry) -> str:
    level = entry.classification.taiwan_level
    lines = [bold(f"🇹🇼 T{level} · {entry.classification.title_zh}"), italic(entry.article.title),
             escape(metadata(entry)), field("一句話重點", [entry.summary.headline_zh]),
             field("與台灣的關聯", [entry.classification.taiwan_link or "未提供"])]
    body = [field(label, values) for label, values in summary_fields(entry.summary, headline=False)]
    if entry.summary.leader_stance:
        body.append(field("📰 經濟學人社論立場", [*merged_leader_titles(digest, entry), entry.summary.leader_stance]))
    if body:
        lines.append(blockquote("\n\n".join(body), expandable=True))
    return "\n\n".join(lines)


def compact_html(digest: Digest, entry: Entry, *, taiwan: bool = False) -> str:
    summary = entry.summary
    label = f"{'🇹🇼 T3 · ' if taiwan else ''}{entry.classification.title_zh}（{summary.tier}）"
    if summary.tier == "E" and not taiwan:
        return bold(label) + " — " + escape(summary.headline_zh)
    lines = [bold(label), italic(entry.article.title), escape(metadata(entry)), escape(summary.headline_zh)]
    if taiwan:
        lines.append(field("與台灣的關聯", [entry.classification.taiwan_link or "未提供"]))
    if summary.tier in ("A", "B"):
        fields = summary_fields(summary, headline=False)
    elif summary.tier == "C" or taiwan:
        fields = [("重點", summary.key_points)] if summary.key_points else []
        if summary.summary_zh:
            fields.append(("摘要", [summary.summary_zh]))
    else:
        fields = []
        if summary.summary_zh:
            lines.append(field("摘要", [summary.summary_zh]))
    if summary.leader_stance:
        fields.append(("📰 經濟學人社論立場", [*merged_leader_titles(digest, entry), summary.leader_stance]))
    if fields:
        lines.append(blockquote("\n\n".join(field(label, values) for label, values in fields), expandable=True))
    return "\n".join(lines)


def english_blocks(digest: Digest) -> list[str]:
    pick, article = digest.english, english_article(digest)
    if pick is None or article is None:
        return [bold("英文學習選文") + "\n本期未選文。"]
    classification = digest.classifications.get(article.id)
    result = [bold("英文學習選文") + "\n" + italic(article.title) + "\n"
              + bold(classification.title_zh if classification else article.title) + "\n\n"
              + field("選文理由", [pick.reason_zh]) + "\n"
              + escape(f"CEFR：{pick.cefr} · 字數：{pick.word_count:,} · 預估閱讀時間：{pick.reading_minutes} 分鐘")
              + "\n\n" + field("背景導讀", [pick.pre_reading_zh])]
    vocabulary = "\n\n".join(bold(item.word) + " " + escape(item.pos) + "\n" + escape(item.meaning_zh)
                                  + "\n" + italic(item.example_en) + ("\n" + escape(item.note_zh) if item.note_zh else "") for item in pick.vocabulary)
    phrases = "\n\n".join(bold(item.phrase) + "\n" + escape(item.meaning_zh) + "\n" + italic(item.example_en) for item in pick.phrases)
    sentences = "\n\n".join(italic(item.sentence_en) + "\n" + escape(item.breakdown_zh) + "\n" + escape("中譯：" + item.translation_zh) for item in pick.sentences)
    for label, content in (("生詞表", vocabulary), ("實用片語", phrases), ("長難句解析", sentences)):
        result.append(bold(label) + "\n" + blockquote(content, expandable=True))
    result.append(field("寫作手法", pick.writing_notes_zh))
    result.append(bold("閱讀理解") + "\n" + "\n".join(escape(f"{i}. {item.question}") for i, item in enumerate(pick.quiz, 1)))
    result.append(blockquote(bold("答案（點開）") + "\n" + "\n".join(escape(f"{i}. {item.answer}") for i, item in enumerate(pick.quiz, 1)), expandable=True))
    return result


def render_telegram(digest: Digest, limit: int = 4000) -> list[str]:
    result = split_html(overview_html(digest), limit)
    groups = sections(digest)
    if not any(section.entries for section in groups[:3]):
        result.extend(split_html("🇹🇼 台灣：本期沒有台灣相關文章。", limit))
    for section in groups[:2]:
        for entry in section.entries:
            result.extend(split_html(full_taiwan_html(digest, entry), limit))
    if groups[2].entries:
        result.extend(pack_blocks([bold("🇹🇼 三、間接相關（T3）"), *[compact_html(digest, entry, taiwan=True) for entry in groups[2].entries]], limit))
    for section in groups[3:]:
        result.extend(pack_blocks([bold(section.title), *[compact_html(digest, entry) for entry in section.entries]], limit))
    result.extend(pack_blocks(english_blocks(digest), limit))
    return result
