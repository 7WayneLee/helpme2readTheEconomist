"""Ordered public study pages; original paragraphs stay in the private chat."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..models import Digest, Source
from ..telegraph.nodes import Node, content_size, node, validate_nodes
from ..telegram.format import blockquote, bold, check_html, escape, link, split_html, strip_tags, utf16_len
from .common import (TAIWAN_TAG, Entry, clean_text, english_article, merged_leader_titles, metadata,
                     ordered_brief, overview, sections, summary_fields, title, word_count_label, source_labels)

GROUPS = (("weekly", "本週導讀"), ("taiwan", "台灣"), ("focus", "本週焦點"), ("international", "國際"),
          ("topics", "財經・科技・文化"), ("english", "英文學習"))
# Random creation titles produce 16 hexadecimal characters plus the date suffix.
PREVIEW_URL = "https://telegra.ph/0000000000000000-00-00"


@dataclass(frozen=True)
class Page:
    key: str
    group: int
    part: int
    title: str
    nodes: list[Node]

    @property
    def label(self) -> str:
        return GROUPS[self.group][1] + (f"（續 {self.part}）" if self.part > 1 else "")


@dataclass(frozen=True)
class _Block:
    headings: tuple[str, ...]
    nodes: list[Node]


def _field(label: str, values: list[str]) -> list[Node]:
    values = [clean_text(value) for value in values]
    result = [node("p", node("b", label))]
    if label == "文章脈絡":
        result.append(node("ol", *[node("li", value) for value in values]))
    elif label == "重要引述":
        result.extend(node("blockquote", *[node("p", line) for line in value.split("\n")]) for value in values)
    elif len(values) > 1:
        result.append(node("ul", *[node("li", value) for value in values]))
    else:
        result.extend(node("p", value) for value in values)
    return result


def article_nodes(digest: Digest, entry: Entry) -> list[Node]:
    if entry.summary.tier == "E":
        result = [node("p", node("b", clean_text(entry.classification.title_zh)), " — ", clean_text(entry.summary.headline_zh))]
    else:
        result = [node("h4", clean_text(entry.classification.title_zh)), node("p", node("i", entry.article.title)),
                  node("p", metadata(entry))]
    if entry.classification.taiwan_level:
        result.extend(_field("與台灣的關聯", [entry.classification.taiwan_link or "未提供"]))
        result.extend(sources_nodes(entry.classification.sources))
    for label, values in summary_fields(entry.summary, headline=entry.summary.tier != "E"):
        result.extend(_field(label, values))
        if label == "對台灣的意涵":
            result.extend(sources_nodes(entry.summary.sources))
    if entry.summary.leader_stance:
        result.append(node("p", node("b", "經濟學人立場")))
        result.extend(node("p", node("i", value)) for value in merged_leader_titles(digest, entry))
        result.append(node("p", clean_text(entry.summary.leader_stance)))
    return result


def sources_nodes(sources: list[Source]) -> list[Node]:
    labels = source_labels(sources)
    children: list[Node] = ["依據："]
    for label, url in labels:
        if len(children) > 1:
            children.append("、")
        children.append(node("a", label, href=url))
    return [node("p", node("i", *children))] if labels else []


def english_nodes(digest: Digest) -> list[Node]:
    pick, article = digest.english, english_article(digest)
    if pick is None or article is None:
        return [node("p", "本期未選文。")]
    classification = digest.classifications.get(article.id)
    result = [node("h4", article.title), node("p", classification.title_zh if classification else article.title)]
    result.extend(_field("選文理由", [pick.reason_zh]))
    result.append(node("p", f"CEFR：{pick.cefr} · {word_count_label(pick.word_count)} · 預估閱讀時間：{pick.reading_minutes} 分鐘"))
    result.extend([node("p", "原文全文請見圖文完整版。"), node("h3", "背景導讀"), node("p", pick.pre_reading_zh), node("h3", "生詞")])
    for item in pick.vocabulary:
        result.extend([node("p", node("b", item.word), f" · {item.pos} · {item.meaning_zh}"),
                       node("p", node("i", item.example_en))])
        if item.note_zh:
            result.append(node("p", "補充：" + item.note_zh))
    result.append(node("h3", "實用片語"))
    for item in pick.phrases:
        result.extend([node("p", node("b", item.phrase), " · " + item.meaning_zh),
                       node("p", node("i", item.example_en))])
    result.append(node("h3", "長難句解析"))
    for item in pick.sentences:
        result.append(node("blockquote", item.sentence_en))
        result.extend(_field("句構", [item.breakdown_zh]))
        result.extend(_field("翻譯", [item.translation_zh]))
    result.extend([node("h3", "寫作手法"), node("ul", *[node("li", value) for value in pick.writing_notes_zh]),
                   node("h3", "閱讀理解"), node("ol", *[node("li", item.question) for item in pick.quiz]),
                   node("hr"), node("h3", "答案"), node("ol", *[node("li", item.answer) for item in pick.quiz])])
    return result


def _logical_blocks(digest: Digest) -> list[list[_Block]]:
    weekly = [_Block((), [node("p", overview(digest))])]
    brief = digest.week_brief
    if brief and (brief.politics or brief.business):
        weekly.append(_Block((), [node("h3", "本週要聞速覽")]))
        for label, items in (("政治", brief.politics), ("商業", brief.business)):
            if items:
                weekly.append(_Block((label,), [node("ul", *[node("li", (TAIWAN_TAG if item.taiwan_related else "") + clean_text(item.text_zh)) for item in ordered_brief(items)])]))
    taiwan: list[_Block] = []
    focus: list[_Block] = []
    international: list[_Block] = []
    topics: list[_Block] = []
    for section in sections(digest):
        if section.anchor.startswith("taiwan-"):
            taiwan.extend(_Block((section.title,), article_nodes(digest, entry)) for entry in section.entries)
        else:
            target = focus if section.anchor == "focus" else international if section.anchor.startswith("intl-") else topics
            target.extend(_Block((section.title,), article_nodes(digest, entry)) for entry in section.entries)
    return [weekly, taiwan, focus, international, topics, [_Block((), english_nodes(digest))] if english_article(digest) else []]


def cover_caption(digest: Digest) -> str:
    cover = next((article for article in digest.issue.articles if article.is_cover), None)
    classification = digest.classifications.get(cover.id) if cover else None
    if classification and classification.title_zh:
        return "本期封面：" + clean_text(classification.title_zh)
    companion = digest.classifications.get(classification.companion_id) if classification and classification.companion_id else None
    return "本期封面：" + clean_text(companion.title_zh if companion else title(digest))


def _clean_nodes(nodes: list[Node]) -> list[Node]:
    return [clean_text(item) if isinstance(item, str)
            else {**item, "children": _clean_nodes(item.get("children", []))} for item in nodes]


def _page(digest: Digest, group: int, part: int, nodes: list[Node], cover_url: str | None = None) -> Page:
    suffix = "（續）" if part > 1 else ""
    heading = f"經濟學人導讀 {digest.issue_date.replace('.', '/')}｜{GROUPS[group][1]}{suffix}"
    if cover_url:
        nodes = [node("figure", node("img", src=cover_url), node("figcaption", cover_caption(digest))), *nodes]
    return Page(f"{GROUPS[group][0]}:{part}", group, part, heading, _clean_nodes(nodes))


def with_navigation(pages: list[Page], urls: dict[str, str]) -> list[Page]:
    result = []
    for index, page in enumerate(pages):
        navigation: list[Node] = []
        for other in pages:
            if navigation:
                navigation.append(" · ")
            navigation.append(node("b", other.label) if other.key == page.key else node("a", other.label, href=urls[other.key]))
        footer: list[Node] = []
        if index > 0:
            footer.append(node("a", "← 上一頁", href=urls[pages[index - 1].key]))
        if index + 1 < len(pages):
            if footer:
                footer.append(" · ")
            footer.append(node("a", "下一頁 →", href=urls[pages[index + 1].key]))
        has_cover = bool(page.nodes and isinstance(page.nodes[0], dict) and page.nodes[0].get("tag") == "figure")
        leading = page.nodes[:1] if has_cover else []
        body = page.nodes[1:] if has_cover else page.nodes
        nodes = [*leading, node("p", *navigation), *body, node("p", *footer)]
        validate_nodes(nodes)
        result.append(replace(page, nodes=nodes))
    return result


def render_telegraph(digest: Digest, page_limit_bytes: int = 60000, *,
                     url_reserve_bytes: int = len(PREVIEW_URL), cover_url: str | None = None) -> list[Page]:
    """Pack indivisible articles, reserving all navigation bytes before publishing.

    A single article (including the English guide) too large for a page raises
    instead of dropping fields or silently exceeding the configured limit.
    """
    if not 1 <= page_limit_bytes <= 64000:
        raise ValueError("Telegraph 頁面上限必須介於 1 與 64000 位元組之間")
    logical = _logical_blocks(digest)
    planned = [_page(digest, group, 1, [], cover_url) for group, blocks in enumerate(logical) if blocks]
    dummy_url = PREVIEW_URL + "x" * max(0, url_reserve_bytes - len(PREVIEW_URL))
    while True:
        # Use a worst-case footer even for the first and last pages.
        footer = node("p", node("a", "← 上一頁", href=dummy_url), " · ", node("a", "下一頁 →", href=dummy_url))
        overhead = max(content_size([*page.nodes[:-1], footer]) for page in with_navigation(
            [_page(digest, page.group, page.part, [], cover_url) for page in planned], {page.key: dummy_url for page in planned}))
        budget = page_limit_bytes - overhead
        packed = []
        for group, blocks in enumerate(logical):
            if not blocks:
                continue
            current: list[Node] = []
            previous_headings: tuple[str, ...] = ()
            part = 1
            for block in blocks:
                common = 0
                while common < min(len(previous_headings), len(block.headings)) and previous_headings[common] == block.headings[common]:
                    common += 1
                addition = [node("h3", label) for label in block.headings[common:]] + block.nodes
                if content_size(current + addition) > budget and current:
                    packed.append(_page(digest, group, part, current, cover_url))
                    part += 1
                    current = []
                    addition = [node("h3", label) for label in block.headings] + block.nodes
                if content_size(addition) > budget:
                    raise ValueError(f"{GROUPS[group][1]}的單篇內容加上導覽超過頁面上限；請提高 telegraph.page_limit_bytes")
                current.extend(addition)
                previous_headings = block.headings
            packed.append(_page(digest, group, part, current, cover_url))
        if [page.key for page in packed] == [page.key for page in planned]:
            return packed
        planned = packed


def summary_message(digest: Digest, pages: list[Page], urls: dict[str, str], *, site_url: str | None = None) -> str:
    lines = ["📰 " + bold(title(digest)), escape(overview(digest))]
    lines.append("")
    lines.extend(link(urls[page.key], page.label) for page in pages)
    if site_url:
        lines.append("🔒 圖文完整版（需帳密）：" + link(site_url, "開啟"))
    message = "\n".join(lines)
    check_html(message)
    if utf16_len(message) > 4000:
        raise ValueError("導讀摘要訊息超過 Telegram 上限")
    return message


def caption_length(html: str) -> int:
    """Telegram counts decoded visible caption text in UTF-16 units."""
    return utf16_len(strip_tags(html))


def summary_caption(digest: Digest, pages: list[Page], urls: dict[str, str]) -> tuple[str, bool]:
    """Return a fitting caption and whether to send the full summary separately."""
    caption = summary_message(digest, pages, urls)
    if caption_length(caption) > 1024:
        return bold(title(digest)), True
    return caption, False


def original_text_messages(digest: Digest, limit: int = 4000) -> list[str]:
    article = english_article(digest)
    if article is None or not article.paragraphs:
        return []
    first = bold("📖 英文選文原文（點開）") + "\n"
    continuation = bold("📖 英文選文原文（續）") + "\n"
    content = "\n\n".join(escape(f"[{number}] {paragraph}") for number, paragraph in enumerate(article.paragraphs, 1))
    pieces = split_html(blockquote(content, expandable=True), limit - max(utf16_len(first), utf16_len(continuation)))
    return [(first if index == 0 else continuation) + piece for index, piece in enumerate(pieces)]
