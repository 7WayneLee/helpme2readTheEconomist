"""A self-contained, mobile-friendly HTML report."""

from __future__ import annotations

import base64
import re
from collections.abc import Callable
from html import escape
from importlib.resources import files

from ..analysis.figures import FIGURE_KINDS, figure_note
from ..models import Digest, Source
from ..images import ArticleImages, ImageBlob, IssueImages, PositionedImage, inline_images_allowed
from ..taxonomy import TIERS
from .common import (TAIWAN_TAG, Entry, clean_text, english_article, generation_time, merged_leader_titles,
                     metadata, ordered_brief, overview, sections, summary_fields, title,
                     word_count_label, source_labels)


def paragraph(value: str) -> str:
    return f"<p>{escape(clean_text(value))}</p>"


def sources_html(sources: list[Source]) -> str:
    labels = source_labels(sources)
    if not labels:
        return ""
    links = "、".join(f'<a href="{escape(url, quote=True)}">{escape(label)}</a>' for label, url in labels)
    return '<p class="sources"><small>依據：' + links + "</small></p>"


def bullets(values: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"


def image_html(blob: ImageBlob, alt: str, *, caption: str | None = None, cover: bool = False) -> str:
    source = f"data:{blob.mime};base64,{base64.b64encode(blob.data).decode('ascii')}"
    attributes = ' class="issue-cover"' if cover else ""
    loading = "" if cover else ' loading="lazy"'
    label = f"<figcaption>{escape(caption)}</figcaption>" if caption else ""
    return f'<figure{attributes}><img src="{escape(source, quote=True)}" alt="{escape(alt, quote=True)}"{loading}>{label}</figure>'


ImageRenderer = Callable[..., str]


def structure_html(values: list[str], inline: list[PositionedImage], render_image: ImageRenderer,
                   alt: str, figure_notes: dict[str, dict] | None = None) -> str:
    def illustrated(blob: ImageBlob) -> str:
        note = (figure_notes or {}).get(blob.name)
        if isinstance(note, dict):
            # Digests made before the short-alt format keep their original layout.
            if "alt_zh" not in note and "takeaway_zh" not in note:
                if (isinstance(note.get("kind"), str) and note["kind"] in FIGURE_KINDS
                        and isinstance(note.get("description_zh"), str) and note["description_zh"]):
                    label = {"chart": "圖表", "map": "地圖"}.get(note["kind"], "配圖")
                    description = note["description_zh"]
                    return render_image(blob, description, caption=f"▲ {label}：{description}")
            else:
                try:
                    note = figure_note(note)
                except ValueError:
                    return render_image(blob, alt)
                description = note["description_zh"]
                if note["kind"] in {"chart", "map"}:
                    label = {"chart": "圖表", "map": "地圖"}[note["kind"]]
                    takeaway = note.get("takeaway_zh")
                    caption = f"▲ {label}｜" + (f"重點：{takeaway}　" if takeaway else "") + description
                else:
                    caption = f"▲ 配圖：{description}"
                return render_image(blob, note["alt_zh"], caption=caption)
        return render_image(blob, alt)

    assignments: dict[int, list[ImageBlob]] = {}
    ranges = []
    for index, value in enumerate(values):
        match = re.match(r"第\s*(\d+)\s*(?:[–—−~～-]\s*(\d+)\s*)?段[：:]", value)
        if match:
            ranges.append((index, int(match[1]), int(match[2] or match[1])))
    for positioned in inline:
        paragraph_number = positioned.before_paragraph + 1
        matching = [index for index, start, end in ranges if start <= paragraph_number <= end]
        preceding = [index for index, start, end in ranges if start <= paragraph_number]
        target = matching[0] if matching else preceding[-1] if preceding else len(values)
        assignments.setdefault(target, []).append(positioned.image)
    result = "<ol>"
    for index, value in enumerate(values):
        result += "<li>" + escape(value)
        result += "".join(illustrated(blob) for blob in assignments.get(index, []))
        result += "</li>"
    result += "</ol>"
    return result + "".join(illustrated(blob) for blob in assignments.get(len(values), []))


def article_html(digest: Digest, entry: Entry, images: IssueImages | None = None,
                 *, render_image: ImageRenderer = image_html) -> str:
    level, tier = entry.classification.taiwan_level, entry.summary.tier
    header = f'<h4>{escape(clean_text(entry.classification.title_zh))}</h4><p lang="en"><i>{escape(entry.article.title)}</i></p>'
    header += paragraph(metadata(entry))
    if level:
        header += f'<span class="badge taiwan t{level}">T{level}</span> '
    header += f'<span class="badge tier">{escape(TIERS[tier])}</span>'
    selected = images.by_article.get(entry.article.id, ArticleImages()) if images else ArticleImages()
    if selected.head:
        header += render_image(selected.head, entry.classification.title_zh + " 插圖")
    headline, *fields = summary_fields(entry.summary)
    relation = ""
    if level:
        relation = "<h5>與台灣的關聯</h5>" + paragraph(clean_text(entry.classification.taiwan_link or "未提供"))
        relation += sources_html(entry.classification.sources)
    body = ""
    for label, values in fields:
        body += f"<h5>{label}</h5>"
        if label == "文章脈絡":
            allowed = inline_images_allowed(tier, level, entry.article.id, digest.focus_ids)
            body += structure_html(values, selected.inline if allowed else [], render_image,
                                   entry.classification.title_zh + " 插圖", digest.figure_notes)
        else:
            body += bullets(values) if len(values) > 1 else paragraph(values[0])
        if label == "對台灣的意涵":
            body += sources_html(entry.summary.sources)
    if entry.summary.leader_stance:
        body += "<h5>經濟學人立場</h5>" + "".join(paragraph(v) for v in merged_leader_titles(digest, entry))
        body += paragraph(clean_text(entry.summary.leader_stance))
    # One-sentence entries have no empty disclosure, even when they have a Taiwan link.
    if body:
        opened = " open" if tier in ("A", "B") or level >= 1 else ""
        body = f"<details{opened}><summary>閱讀摘要</summary>" + body + "</details>"
    return '<article class="story">' + header + "<h5>一句話重點</h5>" + paragraph(headline[1][0]) + relation + body + "</article>"


def brief_html(digest: Digest, images: IssueImages | None = None,
               *, render_image: ImageRenderer = image_html) -> str:
    result = ""
    for label, kind, items in (("政治", "world_politics", digest.week_brief.politics if digest.week_brief else []),
                               ("商業", "world_business", digest.week_brief.business if digest.week_brief else [])):
        if not items:
            continue
        selected = [images.by_article.get(article.id, ArticleImages()) for article in digest.issue.articles
                    if images and article.kind == kind]
        inline = [positioned for item in selected for positioned in item.inline]
        inline.extend(PositionedImage(item.head, 0) for item in selected if item.head)
        result += f"<h3>{label}</h3><ul>"
        for index, item in sorted(enumerate(items), key=lambda pair: not pair[1].taiwan_related):
            badge = f'<span class="badge taiwan">{TAIWAN_TAG}</span> ' if item.taiwan_related else ""
            result += f"<li>{badge}{escape(item.text_zh)}"
            caption = "▲ 配圖：" + item.text_zh[:40] + ("…" if len(item.text_zh) > 40 else "")
            result += "".join(render_image(positioned.image, label + "要聞 插圖", caption=caption)
                              for positioned in inline if positioned.before_paragraph == index)
            result += "</li>"
        result += "</ul>"
    cartoons = []
    if images:
        for article in digest.issue.articles:
            if article.kind == "cartoon" and (selected := images.by_article.get(article.id)):
                cartoons.extend(([selected.head] if selected.head else []) + [item.image for item in selected.inline])
    if cartoons:
        result += "<h3>本週漫畫</h3>" + "".join(render_image(blob, "本週漫畫 插圖") for blob in cartoons)
    return result


def english_html(digest: Digest) -> str:
    pick, article = digest.english, english_article(digest)
    if pick is None or article is None:
        return ""
    classification = digest.classifications.get(article.id)
    result = f'<h3 lang="en">{escape(article.title)}</h3>' + paragraph(classification.title_zh if classification else article.title)
    result += "<h3>選文理由</h3>" + paragraph(pick.reason_zh)
    result += paragraph(f"CEFR：{pick.cefr} · 字數：{word_count_label(pick.word_count)} · 預估閱讀時間：{pick.reading_minutes} 分鐘")
    result += "<h3>背景導讀</h3>" + paragraph(pick.pre_reading_zh)
    result += '<h3>生詞表</h3><div class="study-cards">'
    for item in pick.vocabulary:
        result += '<article class="study-card"><p class="study-term">' + f'<strong lang="en">{escape(item.word)}</strong> <span lang="en">{escape(item.pos)}</span> <span>{escape(item.meaning_zh)}</span></p>'
        result += f'<p class="study-example" lang="en"><i>{escape(item.example_en)}</i></p>'
        if item.note_zh:
            result += paragraph("補充：" + item.note_zh)
        result += "</article>"
    result += '</div><h3>實用片語</h3><div class="study-cards">'
    for item in pick.phrases:
        result += '<article class="study-card"><p class="study-term">' + f'<strong lang="en">{escape(item.phrase)}</strong> <span>{escape(item.meaning_zh)}</span></p>'
        result += f'<p class="study-example" lang="en"><i>{escape(item.example_en)}</i></p></article>'
    result += "</div><h3>長難句解析</h3>"
    for item in pick.sentences:
        result += "<blockquote>" + escape(item.sentence_en) + "</blockquote>" + paragraph(item.breakdown_zh) + paragraph("中譯：" + item.translation_zh)
    result += "<h3>寫作手法</h3>" + bullets(pick.writing_notes_zh) + "<h3>閱讀理解</h3>"
    for number, item in enumerate(pick.quiz, 1):
        result += paragraph(f"{number}. {item.question}")
    if pick.quiz:
        result += "<details><summary>答案（點開）</summary>"
        result += "".join(paragraph(f"{number}. {item.answer}") for number, item in enumerate(pick.quiz, 1))
        result += "</details>"
    result += "<h3>原文全文</h3>"
    for number, value in enumerate(article.paragraphs, 1):
        result += f'<p lang="en"><span class="paragraph-number">[{number}]</span> {escape(value)}</p>'
    return result


def render_html(digest: Digest, images: IssueImages | None = None) -> str:
    groups = sections(digest)
    brief = brief_html(digest, images)
    taiwan = [section for section in groups if section.anchor.startswith("taiwan-")]
    toc = ([("brief", "本週要聞速覽")] if brief else [])
    if taiwan:
        toc.append(("taiwan", "台灣"))
    toc.extend((section.anchor, section.title) for section in groups if not section.anchor.startswith("taiwan-"))
    if english_article(digest):
        toc.append(("english", "英文學習選文"))
    cover = image_html(images.cover, title(digest) + " 封面", cover=True) if images and images.cover else ""
    body = f"<header><h1>{escape(title(digest))}</h1>" + cover + paragraph("產生時間：" + generation_time(digest)) + paragraph(overview(digest)) + "</header>"
    chips = [f'<a class="toc-chip" href="#{anchor}">{escape(label)}</a>' for anchor, label in toc if anchor != "taiwan"]
    if taiwan:
        chips.insert(1, '<span class="toc-group"><a href="#taiwan">台灣</a>' + "".join(
            f'<a href="#{section.anchor}">T{section.anchor[-1]}</a>' for section in taiwan) + '</span>')
    body += '<nav aria-label="目錄"><h2>目錄</h2><div class="toc-chips">' + "".join(chips) + '</div></nav>'
    if brief:
        body += '<section id="brief"><h2>本週要聞速覽</h2>' + brief + '</section>'
    if taiwan:
        body += '<section id="taiwan"><h2>台灣</h2>'
        for section in taiwan:
            body += f'<section id="{section.anchor}"><h3>{escape(section.title)}</h3>'
            body += "".join(article_html(digest, entry, images) for entry in section.entries) + '</section>'
        body += '</section>'
    for section in groups:
        if section.anchor.startswith("taiwan-"):
            continue
        body += f'<section id="{section.anchor}"><h2>{escape(section.title)}</h2>'
        body += "".join(article_html(digest, entry, images) for entry in section.entries) + '</section>'
    if english_article(digest):
        body += '<section id="english"><h2>英文學習選文</h2>' + english_html(digest) + '</section>'
    css = files("econ_digest").joinpath("templates/report.css").read_text(encoding="utf-8")
    result = '<!DOCTYPE html>\n<html lang="zh-TW"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' + f"<title>{escape(title(digest))}</title><style>{css}</style></head><body><main>" + body + "</main></body></html>\n"
    return clean_text(result)
