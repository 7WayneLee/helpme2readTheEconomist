"""A self-contained, mobile-friendly HTML report."""

from __future__ import annotations

from html import escape
from importlib.resources import files

from ..models import Digest
from .common import (Entry, english_article, generation_time, merged_leader_titles,
                     metadata, overview, sections, skipped, statistics, summary_fields, title)


def paragraph(value: str) -> str:
    return f"<p>{escape(value)}</p>"


def bullets(values: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"


def article_html(digest: Digest, entry: Entry) -> str:
    level, tier = entry.classification.taiwan_level, entry.summary.tier
    header = f'<h4>{escape(entry.classification.title_zh)}</h4><p lang="en"><i>{escape(entry.article.title)}</i></p>'
    header += paragraph(metadata(entry))
    header += f'<span class="badge taiwan t{level}">T{level}</span> <span class="badge tier">{escape(tier)}</span>'
    headline, *fields = summary_fields(entry.summary)
    body = ""
    if level:
        body += "<h5>與台灣的關聯</h5>" + paragraph(entry.classification.taiwan_link or "未提供")
    for label, values in fields:
        body += f"<h5>{label}</h5>" + (bullets(values) if len(values) > 1 else paragraph(values[0]))
    if entry.summary.leader_stance:
        body += "<h5>📰 經濟學人社論立場</h5>" + "".join(paragraph(v) for v in merged_leader_titles(digest, entry))
        body += paragraph(entry.summary.leader_stance)
    opened = " open" if tier in ("A", "B") else ""
    return '<article class="story">' + header + "<h5>一句話重點</h5>" + paragraph(headline[1][0]) + f"<details{opened}><summary>閱讀摘要</summary>" + body + "</details></article>"


def english_html(digest: Digest) -> str:
    pick, article = digest.english, english_article(digest)
    if pick is None or article is None:
        return paragraph("本期未選文。")
    classification = digest.classifications.get(article.id)
    result = f'<h3 lang="en">{escape(article.title)}</h3>' + paragraph(classification.title_zh if classification else article.title)
    result += "<h3>選文理由</h3>" + paragraph(pick.reason_zh)
    result += paragraph(f"CEFR：{pick.cefr} · 字數：{pick.word_count:,} · 預估閱讀時間：{pick.reading_minutes} 分鐘")
    result += "<h3>背景導讀</h3>" + paragraph(pick.pre_reading_zh)
    result += '<h3>生詞表</h3><div class="table-scroll"><table><thead><tr>' + "".join(f"<th>{v}</th>" for v in ("word", "詞性", "中文", "原文例句", "補充")) + "</tr></thead><tbody>"
    for item in pick.vocabulary:
        result += "<tr>" + "".join(f"<td>{escape(v)}</td>" for v in (item.word, item.pos, item.meaning_zh, item.example_en, item.note_zh or "")) + "</tr>"
    result += "</tbody></table></div><h3>實用片語</h3>"
    for item in pick.phrases:
        result += f"<h4>{escape(item.phrase)}</h4>" + paragraph(item.meaning_zh) + paragraph(item.example_en)
    result += "<h3>長難句解析</h3>"
    for item in pick.sentences:
        result += "<blockquote>" + escape(item.sentence_en) + "</blockquote>" + paragraph(item.breakdown_zh) + paragraph("中譯：" + item.translation_zh)
    result += "<h3>寫作手法</h3>" + bullets(pick.writing_notes_zh) + "<h3>閱讀理解</h3>"
    for number, item in enumerate(pick.quiz, 1):
        result += paragraph(f"{number}. {item.question}") + "<details><summary>答案（點開）</summary>" + paragraph(item.answer) + "</details>"
    result += "<h3>原文全文</h3>"
    for number, value in enumerate(article.paragraphs, 1):
        result += f'<p lang="en"><span class="paragraph-number">[{number}]</span> {escape(value)}</p>'
    return result


def render_html(digest: Digest) -> str:
    groups = sections(digest)
    toc = [("brief", "本週要聞速覽"), ("taiwan", "台灣"), *[(s.anchor, s.title) for s in groups], ("english", "英文學習選文"), ("appendix", "附錄")]
    body = f"<header><h1>{escape(title(digest))}</h1>" + paragraph("產生時間：" + generation_time(digest)) + paragraph(overview(digest)) + "</header>"
    body += '<nav aria-label="目錄"><h2>目錄</h2><ul>' + "".join(f'<li><a href="#{anchor}">{escape(label)}</a></li>' for anchor, label in toc) + "</ul></nav>"
    body += '<section id="brief"><h2>本週要聞速覽</h2>'
    for label, items in (("政治", digest.week_brief.politics if digest.week_brief else []), ("商業", digest.week_brief.business if digest.week_brief else [])):
        body += f"<h3>{label}</h3>" + bullets([("🇹🇼 " if item.taiwan_related else "") + item.text_zh for item in items])
    body += '</section><section id="taiwan"><h2>台灣</h2>'
    for index, section in enumerate(groups):
        if index == 3:
            body += "</section>"
        heading = "h3" if section.anchor.startswith("taiwan-") else "h2"
        body += f'<section id="{section.anchor}"><{heading}>{escape(section.title)}</{heading}>'
        body += "".join(article_html(digest, entry) for entry in section.entries) if section.entries else paragraph("本期沒有這類文章。")
        body += "</section>"
    if len(groups) == 3:
        body += "</section>"
    body += '<section id="english"><h2>英文學習選文</h2>' + english_html(digest) + "</section>"
    body += '<section id="appendix"><h2>附錄</h2><h3>略過項目</h3>' + bullets([f"{name}（{reason}）" for name, reason in skipped(digest)])
    body += "<h3>處理統計</h3>" + bullets(statistics(digest))
    if digest.warnings:
        body += "<h3>注意事項</h3>" + bullets(digest.warnings)
    css = files("econ_digest").joinpath("templates/report.css").read_text(encoding="utf-8")
    return '<!DOCTYPE html>\n<html lang="zh-TW"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' + f"<title>{escape(title(digest))}</title><style>{css}</style></head><body><main>" + body + "</section></main></body></html>\n"
