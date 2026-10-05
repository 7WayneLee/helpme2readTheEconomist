"""Readable Markdown report with a complete English study guide."""

from __future__ import annotations

from html import escape

from ..models import Digest
from .common import (TAIWAN_TAG, Entry, english_article, generation_time, merged_leader_titles,
                     metadata, ordered_brief, overview, sections, skipped, statistics, summary_fields, title,
                     word_count_label)


def text(value: str) -> str:
    return escape(value, quote=False).replace("\\", "\\\\").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")


def article_lines(digest: Digest, entry: Entry) -> list[str]:
    level = f" · T{entry.classification.taiwan_level}" if entry.classification.taiwan_level else ""
    result = [f"### {text(entry.classification.title_zh)}", "", f"*{text(entry.article.title)}*", "",
              f"{text(metadata(entry))}{level}", ""]
    if entry.classification.taiwan_level:
        result.extend(["**與台灣的關聯**", "", text(entry.classification.taiwan_link or "未提供"), ""])
    for label, values in summary_fields(entry.summary):
        result.extend([f"**{label}**", ""])
        result.extend([f"- {text(value)}" for value in values] if len(values) > 1 else [text(values[0])])
        result.append("")
    if entry.summary.leader_stance:
        result.extend(["**📰 經濟學人社論立場**", "",
                       *[f"*{text(value)}*" for value in merged_leader_titles(digest, entry)],
                       text(entry.summary.leader_stance), ""])
    return result


def english_lines(digest: Digest) -> list[str]:
    pick, article = digest.english, english_article(digest)
    if pick is None or article is None:
        return ["本期未選文。", ""]
    classification = digest.classifications.get(article.id)
    lines = [f"### {text(article.title)}", "", text(classification.title_zh if classification else article.title), "",
             f"**選文理由**：{text(pick.reason_zh)}", "",
             f"CEFR：{text(pick.cefr)} · 字數：{word_count_label(pick.word_count)} · 預估閱讀時間：{pick.reading_minutes} 分鐘", "",
             "### 背景導讀", "", text(pick.pre_reading_zh), "", "### 生詞表", ""]
    for item in pick.vocabulary:
        lines.extend([f"**{text(item.word)}** · {text(item.pos)} · {text(item.meaning_zh)}", "",
                      f"*{text(item.example_en)}*", ""])
        if item.note_zh:
            lines.extend(["補充：" + text(item.note_zh), ""])
        lines.extend(["---", ""])
    lines.extend(["", "### 實用片語", ""])
    for item in pick.phrases:
        lines.extend([f"**{text(item.phrase)}** · {text(item.meaning_zh)}", "", f"*{text(item.example_en)}*", "", "---", ""])
    lines.extend(["", "### 長難句解析", ""])
    for item in pick.sentences:
        lines.extend([f"> {text(item.sentence_en)}", "", text(item.breakdown_zh), "", f"中譯：{text(item.translation_zh)}", ""])
    lines.extend(["### 寫作手法", "", *[f"- {text(v)}" for v in pick.writing_notes_zh], "", "### 閱讀理解", ""])
    for number, item in enumerate(pick.quiz, 1):
        lines.extend([f"{number}. {text(item.question)}", "", "<details><summary>答案（點開）</summary>", "", text(item.answer), "", "</details>", ""])
    lines.extend(["### 原文全文", ""])
    for number, paragraph in enumerate(article.paragraphs, 1):
        lines.extend([f"[{number}] {text(paragraph)}", ""])
    return lines


def render_markdown(digest: Digest) -> str:
    groups = sections(digest)
    toc = [("brief", "本週要聞速覽"), ("taiwan", "台灣"), *[(s.anchor, s.title) for s in groups],
           ("english", "英文學習選文"), ("appendix", "附錄")]
    lines = [f"# {text(title(digest))}", "", f"產生時間：{generation_time(digest)}", "", text(overview(digest)), "", "## 目錄", "",
             *[f"- [{label}](#{anchor})" for anchor, label in toc], "", '<a id="brief"></a>', "## 本週要聞速覽", ""]
    for label, items in (("政治", digest.week_brief.politics if digest.week_brief else []),
                         ("商業", digest.week_brief.business if digest.week_brief else [])):
        lines.extend([f"### {label}", "", *[f"- {TAIWAN_TAG if item.taiwan_related else ''}{text(item.text_zh)}"
                                            for item in ordered_brief(items)], ""])
    lines.extend(['<a id="taiwan"></a>', "## 台灣", ""])
    for section in groups:
        lines.extend([f'<a id="{section.anchor}"></a>', f"{'###' if section.anchor.startswith('taiwan-') else '##'} {section.title}", ""])
        if not section.entries:
            lines.extend(["本期沒有這類文章。", ""])
        for entry in section.entries:
            content = article_lines(digest, entry)
            if section.anchor.startswith("taiwan-"):
                content[0] = "#" + content[0]
            lines.extend(content)
    lines.extend(['<a id="english"></a>', "## 英文學習選文", "", *english_lines(digest),
                  '<a id="appendix"></a>', "## 附錄", "", "### 略過項目", "",
                  *[f"- {text(name)}（{reason}）" for name, reason in skipped(digest)], "", "### 處理統計", "",
                  *[f"- {text(value)}" for value in statistics(digest)], ""])
    if digest.warnings:
        lines.extend(["### 注意事項", "", *[f"- {text(value)}" for value in digest.warnings], ""])
    return "\n".join(lines).rstrip() + "\n"
