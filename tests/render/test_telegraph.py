from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from econ_digest.models import Digest
from econ_digest.render.common import english_article
from econ_digest.render.telegraph import (article_nodes, original_text_messages, render_telegraph,
                                        summary_message, with_navigation)
from econ_digest.telegraph import content_size, validate_nodes
from econ_digest.telegram.format import check_html, strip_tags, utf16_len


def all_text(nodes: list) -> str:
    return "\n".join(item if isinstance(item, str) else all_text(item.get("children", [])) for item in nodes)


def test_four_pages_order_and_complete_fields(sample_digest: Digest) -> None:
    pages = render_telegraph(sample_digest)
    assert [page.key for page in pages] == ["weekly:1", "international:1", "topics:1", "english:1"]
    assert pages[0].title == "經濟學人導讀 2026/10/03｜① 本週導讀"
    first = all_text(pages[0].nodes)
    for text in ("本週要聞速覽", "政治", "商業", "台灣", "一、台灣本身", "二、台灣與國際", "三、間接相關",
                 "與台灣的關聯", "背景", "文章脈絡", "主張：", "證據：", "反方觀點：", "結論：",
                 "重要引述", "中譯：", "對台灣的意涵", "延伸思考", "📰 經濟學人社論立場"):
        assert text in first
    assert first.index("台灣相關政治要聞") < first.index("非台灣政治要聞")
    assert "🇹🇼" in first
    international = all_text(pages[1].nodes)
    assert [international.index(label) for label in ("美國", "中國", "亞太", "歐洲", "其他地區")] == sorted(
        international.index(label) for label in ("美國", "中國", "亞太", "歐洲", "其他地區"))
    topics = all_text(pages[2].nodes)
    assert [topics.index(label) for label in ("財經商業", "科技", "科學", "文化生活")] == sorted(
        topics.index(label) for label in ("財經商業", "科技", "科學", "文化生活"))
    assert '"tag": "ol"' in json.dumps(pages[0].nodes)
    assert '"tag": "blockquote"' in json.dumps(pages[0].nodes)
    assert "特別報導" in first and "封面故事" in first
    assert "社論主張持續合作" in first
    merged_leader = next(article for article in sample_digest.issue.articles if article.kind == "leader")
    assert merged_leader.title in first


def test_empty_taiwan_headings_always_present(no_taiwan_digest: Digest) -> None:
    first = all_text(render_telegraph(no_taiwan_digest)[0].nodes)
    assert first.count("本期沒有這類文章。") == 3
    assert all(label in first for label in ("一、台灣本身", "二、台灣與國際", "三、間接相關"))


def test_public_guide_has_answers_at_bottom_and_no_full_text(sample_digest: Digest) -> None:
    pick = english_article(sample_digest)
    assert pick is not None
    long_original = "This copyrighted synthetic paragraph must never become a public page. " * 50
    pick.paragraphs.append(long_original)
    pages = render_telegraph(sample_digest)
    for page in pages:
        validate_nodes(page.nodes)
        assert long_original not in json.dumps(page.nodes, ensure_ascii=False)
    guide = pages[-1].nodes
    assert guide[-3]["tag"] == "hr"
    assert guide[-2]["children"] == ["答案"]
    assert "costs remain" in all_text(guide[-1:])
    text = all_text(guide)
    assert "原文全文已私訊傳送（不公開）。" in text
    assert text.index("閱讀理解") < text.index("答案")
    assert "句構" in text and "翻譯" in text
    assert "CEFR：B1 · 英文 720 字" in text


def test_all_pages_have_current_and_prev_next_navigation(sample_digest: Digest) -> None:
    pages = render_telegraph(sample_digest)
    urls = {page.key: f"https://telegra.ph/test-{index}" for index, page in enumerate(pages)}
    for index, page in enumerate(with_navigation(pages, urls)):
        validate_nodes(page.nodes)
        navigation = page.nodes[0]
        current = navigation["children"][index * 2]
        assert current["tag"] == "b"
        for other in pages:
            if other.key != page.key:
                assert urls[other.key] in json.dumps(navigation)
        footer = all_text(page.nodes[-1:])
        assert ("← 上一頁" in footer) == (index > 0)
        assert ("下一頁 →" in footer) == (index < len(pages) - 1)


def test_split_articles_stay_whole_and_include_navigation_budget(sample_digest: Digest) -> None:
    digest = deepcopy(sample_digest)
    # Populate one category with articles larger than the tiny empty sections.
    base = digest.issue.articles[8]
    for number in range(8):
        article = replace(base, id=f"extra-{number}", order=100 + number, title=f"Whole English article {number}")
        digest.issue.articles.append(article)
        digest.classifications[article.id] = replace(digest.classifications[base.id], article_id=article.id,
                                                    title_zh=f"完整文章 {number}")
        digest.summaries[article.id] = replace(digest.summaries[base.id], article_id=article.id,
                                              summary_zh=(f"只屬於文章 {number} 的摘要。" * 90))
    pages = render_telegraph(digest, 10000)
    assert len(pages) > 4
    assert any(page.title.endswith("（續）") for page in pages)
    urls = {page.key: f"https://telegra.ph/{index:016x}-10-05" for index, page in enumerate(pages)}
    for page in with_navigation(pages, urls):
        assert content_size(page.nodes) <= 10000
    for number in range(8):
        matches = [page for page in pages if f"完整文章 {number}" in all_text(page.nodes)]
        assert len(matches) == 1
        assert f"只屬於文章 {number} 的摘要。" * 90 in all_text(matches[0].nodes)


def test_oversized_single_article_fails_without_truncation(sample_digest: Digest) -> None:
    sample_digest.summaries[sample_digest.issue.articles[0].id].background = "台灣" * 12000
    with pytest.raises(ValueError, match="單篇"):
        render_telegraph(sample_digest)


def test_summary_only_four_primary_links_and_taiwan_priority(sample_digest: Digest) -> None:
    pages = render_telegraph(sample_digest)
    urls = {page.key: f"https://telegra.ph/{index}" for index, page in enumerate(pages)}
    summary = summary_message(sample_digest, pages, urls)
    check_html(summary)
    assert "📰 <b>經濟學人導讀" in summary
    assert "台灣 T1 1 篇、T2 1 篇、T3 1 篇" in summary
    assert summary.count("🇹🇼") == 3 and summary.count("<a ") == 4
    assert summary.index("🇹🇼 台灣晶片展望") < summary.index("🇹🇼 台灣與國際合作") < summary.index("🇹🇼 供應鏈間接影響")
    assert "①" in summary and "④" in summary and "本週導讀：要聞與台灣" in summary


def test_private_original_split_heading_numbering_and_escaping(sample_digest: Digest) -> None:
    article = english_article(sample_digest)
    assert article is not None
    article.paragraphs = ["Long & <invented> original 😊 sentence. " * 250, "第二段原文 " * 900, "最後一段。"]
    messages = original_text_messages(sample_digest)
    assert len(messages) > 3
    assert "📖 英文選文原文（點開）" in messages[0]
    assert all("📖 英文選文原文（續）" in message for message in messages[1:])
    for message in messages:
        check_html(message)
        assert utf16_len(message) <= 4000
        assert "<blockquote expandable>" in message
    full = "".join(strip_tags(message).split("\n", 1)[1] for message in messages)
    assert full == "\n\n".join(f"[{number}] {paragraph}" for number, paragraph in enumerate(article.paragraphs, 1))


def test_no_english_pick(sample_digest: Digest) -> None:
    sample_digest.english = None
    assert original_text_messages(sample_digest) == []
    assert "本期未選文。" in all_text(render_telegraph(sample_digest)[-1].nodes)
