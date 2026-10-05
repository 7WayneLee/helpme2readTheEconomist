from __future__ import annotations

from copy import deepcopy
from collections.abc import Callable
from html.parser import HTMLParser
import json
from pathlib import Path
import re

import pytest

from econ_digest.models import BriefItem, Digest
from econ_digest.render import render_html, render_markdown, render_telegram, write_outputs
from econ_digest.render.telegram import overview_html
from econ_digest.taxonomy import CATEGORY_SHORT_LABELS, TIERS
from econ_digest.telegram.format import check_html, utf16_len


class BalancedHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.links: list[str] = []
        self.details: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag not in ("meta", "br", "hr", "img", "input", "link"):
            self.stack.append(tag)
        if tag == "a":
            self.links.append(values.get("href") or "")
        if tag == "details":
            self.details.append(values)
        assert tag not in ("script", "iframe", "img", "link")
        assert not any(key.startswith("on") for key in values)

    def handle_endtag(self, tag: str) -> None:
        assert self.stack.pop() == tag


def test_markdown_sections_and_complete_fields(sample_digest: Digest) -> None:
    report = render_markdown(sample_digest)
    assert report.startswith("# 經濟學人導讀｜2026 年 10 月 3 日號")
    assert "2026-10-04 10:30（台北時間）" in report
    expected = ["## 本週要聞速覽", "## 台灣", "### 一、台灣本身", "### 二、台灣與國際", "### 三、間接相關",
                *["## " + label for label in CATEGORY_SHORT_LABELS.values()], "## 英文學習選文", "## 附錄"]
    assert [report.index(value) for value in expected] == sorted(report.index(value) for value in expected)
    for field in ("一句話重點", "背景", "文章脈絡", "論證", "主張", "證據", "反方觀點", "結論", "關鍵數據", "重要引述",
                  "經濟學人的立場與盲點", "對台灣的意涵", "延伸思考", "重點", "摘要", "與台灣的關聯",
                  "📰 經濟學人社論立場", "選文理由", "背景導讀", "生詞表", "實用片語", "長難句解析", "寫作手法", "閱讀理解", "原文全文"):
        assert field in report
    assert "A synthetic cover argument" in report
    assert "社論主張持續合作。" in report
    assert "[1] A synthetic &lt;script&gt;" in report
    assert "Token：350" in report and "synthetic-other" in report
    assert "<script>" not in report
    assert "&amp;" in report


def test_empty_t1_and_no_taiwan(sample_digest: Digest, no_taiwan_digest: Digest) -> None:
    sample_digest.classifications["sample-1"].taiwan_level = 0
    report = render_markdown(sample_digest)
    assert "### 一、台灣本身\n\n本期沒有這類文章。" in report
    for render in (render_markdown, render_html):
        assert render(no_taiwan_digest).count("本期沒有這類文章。") == 3
    assert "本期沒有台灣相關文章。" in "\n".join(render_telegram(no_taiwan_digest))


@pytest.mark.parametrize("no_taiwan", [False, True])
def test_html_balance_escape_and_details(sample_digest: Digest, no_taiwan_digest: Digest, no_taiwan: bool) -> None:
    report = render_html(no_taiwan_digest if no_taiwan else sample_digest)
    parser = BalancedHTML()
    parser.feed(report)
    parser.close()
    assert not parser.stack
    assert parser.links and all(link.startswith("#") for link in parser.links)
    assert "&lt;script&gt;" in report and "&amp;" in report
    assert "prefers-color-scheme:dark" in report and 'lang="zh-TW"' in report
    assert len([attrs for attrs in parser.details if "open" in attrs]) == 2
    assert '<details><summary>答案（點開）</summary>' in report
    assert "[1]" in report and "Synthetic quiz answer" in report


def test_article_sort_by_tier_then_reading_order(no_taiwan_digest: Digest) -> None:
    digest = no_taiwan_digest
    for article_id in ("sample-1", "sample-2", "sample-4"):
        digest.classifications[article_id].category = "intl.us"
    digest.issue.articles[0].order = 100
    digest.issue.articles[1].order = 0
    for render in (render_markdown, render_html):
        report = render(digest)
        assert report.index("台灣晶片展望") < report.index("台灣與國際合作") < report.index("美國政策")


def test_telegram_order_limits_and_quiz_answers(sample_digest: Digest) -> None:
    messages = render_telegram(sample_digest)
    for message in messages:
        check_html(message)
        assert utf16_len(message) <= 4000
    all_text = "\n".join(messages)
    assert messages[0].startswith("📰 <b>經濟學人導讀")
    assert messages[0].index("台灣相關政治要聞") < messages[0].index("非台灣政治要聞")
    expected = ["🇹🇼 T1", "🇹🇼 T2", "三、間接相關", "<b>美國</b>", "<b>中國</b>", "<b>亞太</b>", "<b>歐洲</b>",
                "<b>其他地區</b>", "<b>財經商業</b>", "<b>科技</b>", "<b>科學</b>", "<b>文化生活</b>"]
    positions = [all_text.index(value) for value in expected]
    assert positions == sorted(positions)
    assert '<blockquote expandable><b>答案（點開）</b>\n1. Synthetic quiz answer: costs remain.</blockquote>' in all_text
    assert "&lt;script&gt;" in all_text and "<script>" not in all_text
    assert "社論主張持續合作。" in all_text and "A synthetic cover argument" in all_text


@pytest.mark.parametrize("limit", [4000, 500, 200])
def test_long_telegram_fields_are_split(sample_digest: Digest, limit: int) -> None:
    digest = deepcopy(sample_digest)
    digest.summaries["sample-1"].background = "長篇合成資料 😀 & < 比較。\n" * 700
    digest.english.vocabulary[0].note_zh = "生詞補充 😀。" * 700  # type: ignore[union-attr]
    digest.week_brief.politics.extend(BriefItem("合成要聞。" * 60) for _ in range(20))  # type: ignore[union-attr]
    messages = render_telegram(digest, limit)
    assert len(messages) > 20
    for message in messages:
        check_html(message)
        assert utf16_len(message) <= limit
    assert "長篇合成資料" in "".join(messages)


def test_write_outputs(sample_digest: Digest, tmp_path: Path) -> None:
    paths = write_outputs(sample_digest, tmp_path)
    assert {path.name for path in paths.values()} == {"report.md", "report.html", "telegram_messages.json"}
    assert paths["markdown"].read_text(encoding="utf-8") == render_markdown(sample_digest)
    assert paths["html"].read_text(encoding="utf-8") == render_html(sample_digest)
    assert json.loads(paths["telegram"].read_text(encoding="utf-8")) == render_telegram(sample_digest)


def test_telegram_brief_shows_each_item_once(sample_digest: Digest) -> None:
    assert sample_digest.week_brief is not None
    sample_digest.week_brief.politics = [BriefItem(f"政治要聞 {i:02}") for i in range(11)]
    sample_digest.week_brief.politics.insert(2, BriefItem("台灣政治要聞唯一標記", True))
    sample_digest.week_brief.business = [BriefItem(f"商業要聞 {i:02}") for i in range(7)]
    sample_digest.week_brief.business.insert(6, BriefItem("台灣商業要聞唯一標記", True))
    rendered = overview_html(sample_digest)
    visible, hidden = rendered.split("<blockquote expandable>", 1)
    hidden = hidden.split("</blockquote>", 1)[0]
    assert "其餘政治要聞（3 則）" in hidden and "其餘商業要聞（2 則）" in hidden
    for label, count, shown in (("政治", 11, 8), ("商業", 7, 5)):
        for index in range(count):
            marker = f"{label}要聞 {index:02}"
            assert rendered.count(marker) == 1
            assert (marker in visible) == (index < shown)
            assert (marker in hidden) == (index >= shown)
    for marker in ("台灣政治要聞唯一標記", "台灣商業要聞唯一標記"):
        assert rendered.count(marker) == 1 and marker in visible and marker not in hidden
    assert visible.index("台灣政治要聞唯一標記") < visible.index("政治要聞 00")
    check_html(rendered)


@pytest.mark.parametrize("extra_politics,extra_business", [(0, 0), (1, 0), (0, 1)])
def test_telegram_brief_omits_empty_remainder(sample_digest: Digest, extra_politics: int, extra_business: int) -> None:
    assert sample_digest.week_brief is not None
    sample_digest.week_brief.politics = [BriefItem(f"政治 {i}") for i in range(8 + extra_politics)]
    sample_digest.week_brief.business = [BriefItem(f"商業 {i}") for i in range(5 + extra_business)]
    rendered = overview_html(sample_digest)
    assert ("<blockquote expandable>" in rendered) == bool(extra_politics or extra_business)
    assert ("其餘政治要聞（1 則）" in rendered) == bool(extra_politics)
    assert ("其餘商業要聞（1 則）" in rendered) == bool(extra_business)
    assert "（0 則）" not in rendered


def test_tier_letters_are_internal_and_taiwan_levels_stay(sample_digest: Digest) -> None:
    markdown = render_markdown(sample_digest)
    html = render_html(sample_digest)
    telegram = "\n".join(render_telegram(sample_digest))
    assert "### 美國政策\n" in markdown and "<h4>美國政策</h4>" in html and "<b>美國政策</b>" in telegram
    for tier in "ABCDE":
        assert f"（{tier}）" not in markdown + html + telegram
        assert f'<span class="badge tier">{tier}</span>' not in html
        assert f'<span class="badge tier">{TIERS[tier]}</span>' in html
    assert re.search(r" · [A-E](?:\n|$)", markdown) is None
    for report in (markdown, html, telegram):
        assert all(level in report for level in ("T1", "T2", "T3"))
        assert "T0" not in report


@pytest.mark.parametrize("renderer", [render_markdown, render_html, render_telegram])
def test_word_counts_explicitly_describe_english(sample_digest: Digest,
                                               renderer: Callable[[Digest], str | list[str]]) -> None:
    sample_digest.issue.articles[0].word_count = 958
    assert sample_digest.english is not None
    sample_digest.english.word_count = 958
    rendered = renderer(sample_digest)
    report = "\n".join(rendered) if isinstance(rendered, list) else rendered
    assert report.count("英文 958 字") == 2
    assert "字數：英文 958 字" in report
    assert re.search(r"(?<!英文 )958 字", report) is None
