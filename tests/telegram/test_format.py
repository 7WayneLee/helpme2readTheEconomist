from __future__ import annotations

from collections.abc import Callable
import random

import pytest

from econ_digest.telegram.format import (
    blockquote,
    bold,
    check_html,
    code,
    escape,
    italic,
    link,
    pack_blocks,
    split_html,
    strip_tags,
    underline,
    utf16_len,
)


def assert_chunks(chunks: list[str], limit: int, text: str) -> None:
    assert chunks
    for chunk in chunks:
        assert utf16_len(chunk) <= limit
        check_html(chunk)
    assert "".join(strip_tags(chunk) for chunk in chunks) == text


def test_escape() -> None:
    assert escape('台灣 & <晶片> "人工智慧"') == '台灣 &amp; &lt;晶片&gt; "人工智慧"'
    assert escape("&amp;") == "&amp;amp;"


@pytest.mark.parametrize("builder,tag", [(bold, "b"), (italic, "i"), (underline, "u"), (code, "code")])
def test_text_builders(builder: Callable[[str], str], tag: str) -> None:
    html = builder("<台灣>&")
    assert html == f"<{tag}>&lt;台灣&gt;&amp;</{tag}>"
    check_html(html)


def test_link_attribute_escaping() -> None:
    html = link('https://example.test/?a=1&b="<台灣>"', "報導 & 分析")
    assert html == '<a href="https://example.test/?a=1&amp;b=&quot;&lt;台灣&gt;&quot;">報導 &amp; 分析</a>'
    check_html(html)


def test_blockquotes() -> None:
    assert blockquote(bold("台灣")) == "<blockquote><b>台灣</b></blockquote>"
    assert blockquote(bold("台灣"), True) == "<blockquote expandable><b>台灣</b></blockquote>"
    with pytest.raises(ValueError):
        blockquote("<script>bad</script>")


@pytest.mark.parametrize("text,length", [("", 0), ("abc", 3), ("台灣", 2), ("📌", 2), ("🇹🇼", 4), ("台灣📌🇹🇼", 8)])
def test_utf16_len(text: str, length: int) -> None:
    assert utf16_len(text) == length


@pytest.mark.parametrize(
    "html",
    [
        "",
        "台灣\n晶片",
        '<blockquote expandable><b>台灣<i>晶片</i></b></blockquote>',
        '<a href="https://example.test/?x=1&amp;y=&quot;a&quot;">連結</a>',
        "<a href='https://example.test'>連結</a>",
        "<pre><code>&lt;&gt;&amp;&quot;&#128204;&#21488;</code></pre>",
        "<u><s>文字</s></u>",
    ],
)
def test_check_html_valid(html: str) -> None:
    check_html(html)


@pytest.mark.parametrize(
    "html",
    [
        "<b>未結束",
        "</b>",
        "<b><i>錯誤</b></i>",
        "<b>完成</b></b>",
        "<div>內容</div>",
        "<script>alert(1)</script>",
        "<b style='red'>文字</b>",
        "<blockquote hidden>文字</blockquote>",
        "<a>沒有網址</a>",
        '<a href="https://example.test" onclick="bad">文字</a>',
        '<a href="https://example.test?a=1&b=2">文字</a>',
        "<a href=https://example.test>文字</a>",
        "<b/>",
        "<!-- comment -->",
        "<b",
        "台灣 & 晶片",
        "&amp",
        "&unknown;",
        "&#x1F4CC;",
        "&#nope;",
        "&#;",
        "<b>字</b attr>",
    ],
)
def test_check_html_invalid(html: str) -> None:
    with pytest.raises(ValueError):
        check_html(html)


def test_split_demo_long_chinese() -> None:
    text = "台灣晶片與人工智慧" * 1000
    assert len(text) == 9000
    chunks = split_html(blockquote(escape(text), expandable=True))
    assert len(chunks) == 3
    assert [utf16_len(chunk) for chunk in chunks] == [4000, 4000, 1108]
    assert_chunks(chunks, 4000, text)
    assert all(chunk.startswith("<blockquote expandable>") for chunk in chunks)


def test_split_header_keeps_blockquote_text_in_first_chunk() -> None:
    header = bold("本週重點" * 50) + "\n\n"
    text = "\n".join(["台灣晶片與人工智慧。" * 150] * 4)
    chunks = split_html(header + blockquote(escape(text), expandable=True))
    assert chunks[0].startswith(header + "<blockquote expandable>")
    assert "台灣晶片與人工智慧。" in chunks[0]
    assert utf16_len(chunks[0]) >= 4000 * 0.6
    assert [utf16_len(chunk) for chunk in chunks] == [3247, 3037]
    assert_chunks(chunks, 4000, strip_tags(header) + text)
    assert chunks[1].startswith("<blockquote expandable>")


def test_split_only_early_blank_line_still_fills_chunks() -> None:
    text = "標題\n\n" + "台灣晶片與人工智慧" * 1000
    chunks = split_html(text)
    assert [utf16_len(chunk) for chunk in chunks] == [4000, 4000, 1004]
    assert_chunks(chunks, 4000, text)


def test_split_farthest_boundary_when_none_reaches_minimum_fill() -> None:
    html = "台\n\n甲\n&#128204;"
    chunks = split_html(html, 10)
    assert chunks == ["台\n\n甲\n", "&#128204;"]
    assert_chunks(chunks, 10, strip_tags(html))


def test_split_boundary_at_exact_minimum_fill() -> None:
    text = "甲乙丙丁\n\n" + "台灣" * 10
    chunks = split_html(text, 10)
    assert chunks[0] == "甲乙丙丁\n\n"
    assert_chunks(chunks, 10, text)


def test_split_nested_tags_reopens_attributes() -> None:
    text = "台灣📌" * 100
    html = blockquote(bold(text), expandable=True)
    chunks = split_html(html, 100)
    assert len(chunks) > 2
    assert_chunks(chunks, 100, text)
    assert all(chunk.startswith("<blockquote expandable><b>") for chunk in chunks)
    assert all(chunk.endswith("</b></blockquote>") for chunk in chunks)


def test_split_links_reopens_attributes() -> None:
    html = link('https://example.test/?a=1&b="2"', "台灣" * 200)
    chunks = split_html(html, 120)
    assert_chunks(chunks, 120, "台灣" * 200)
    assert all(chunk.startswith('<a href="https://example.test/?a=1&amp;b=&quot;2&quot;">') for chunk in chunks)


def test_split_entities_never_break() -> None:
    html = "&amp;台灣&#128204;" * 100
    chunks = split_html(html, 31)
    assert_chunks(chunks, 31, strip_tags(html))
    assert all(not chunk.endswith(("&", "&a", "&am", "&amp", "&#128")) for chunk in chunks)


@pytest.mark.parametrize(
    "text,limit,expected",
    [
        ("第一段\n\n第二段\n繼續內容很多", 12, "第一段\n\n第二段\n"),
        ("第一行\n第二句。繼續內容很多", 10, "第一行\n第二句。"),
        ("台灣。後續分析很多字", 8, "台灣。後續分析很"),
        ("Done. Next words are lengthy", 15, "Done. Next word"),
        ("What? More words here", 12, "What? More w"),
        ("abc.defghijk", 8, "abc.defg"),
        ("第一段有內容\n\n第二段\n繼續內容很多", 12, "第一段有內容\n\n"),
        ("第一行有足夠內容\n第二句。繼續內容很多", 14, "第一行有足夠內容\n"),
        ("台灣晶片發展。後續分析很多字", 10, "台灣晶片發展。"),
        ("This is done. Next words are lengthy", 20, "This is done."),
        ("What's next? More words here", 18, "What's next?"),
    ],
)
def test_split_boundary_preference(text: str, limit: int, expected: str) -> None:
    chunks = split_html(text, limit)
    assert chunks[0] == expected
    assert_chunks(chunks, limit, text)


def test_split_emoji_counts_source_utf16() -> None:
    chunks = split_html("📌" * 9, 5)
    assert chunks == ["📌📌", "📌📌", "📌📌", "📌📌", "📌"]


def test_split_whole_input_is_preserved() -> None:
    html = "<b>台灣</b>\n\n<i>晶片</i>"
    assert split_html(html, utf16_len(html)) == [html]
    assert split_html("") == [""]


@pytest.mark.parametrize("html,limit", [("text", 0), ("text", -1), ("&amp;", 4), ("<b>台</b>", 7), ("<b>台", 4000)])
def test_split_impossible_or_invalid(html: str, limit: int) -> None:
    with pytest.raises(ValueError):
        split_html(html, limit)


def test_split_nested_varied_markup_roundtrip() -> None:
    generator = random.Random(41)
    alphabet = ["台灣", "📌", "🇹🇼", "&", "<", "\n", "。", "abc. "]
    for _ in range(20):
        text = "".join(generator.choice(alphabet) for _ in range(50))
        html = blockquote(bold(text[:30]) + "\n" + italic(text[30:]), True)
        assert_chunks(split_html(html, 90), 90, text[:30] + "\n" + text[30:])


def test_pack_blocks_greedy_and_ordered() -> None:
    assert pack_blocks(["aaa", "bbb", "cccc", "d"], 8) == ["aaa\n\nbbb", "cccc\n\nd"]
    assert pack_blocks([bold("台灣"), italic("晶片")], 40) == ["<b>台灣</b>\n\n<i>晶片</i>"]
    assert pack_blocks([], 10) == []
    assert pack_blocks([""], 10) == []


def test_pack_blocks_oversized_continuation() -> None:
    text = "台灣晶片📌" * 30
    messages = pack_blocks(["先", blockquote(bold(text), True), "後"], 80)
    assert messages[0] == "先"
    assert messages[1].startswith("<blockquote expandable><b>")
    assert any(message.startswith("（續）\n<blockquote expandable><b>") for message in messages[2:])
    for message in messages:
        assert utf16_len(message) <= 80
        check_html(message)
    decoded = "".join(strip_tags(message).removeprefix("（續）\n") for message in messages)
    assert decoded.replace("\n\n", "") == "先" + text + "後"


def test_pack_custom_continuation_prefix_escaped() -> None:
    messages = pack_blocks(["台灣" * 20], 18, continuation_prefix="<&> ")
    assert messages[1].startswith("&lt;&amp;&gt; ")
    assert all(utf16_len(message) <= 18 for message in messages)
    for message in messages:
        check_html(message)


@pytest.mark.parametrize("blocks,limit,prefix", [([], 0, "x"), (["<b>"], 20, "x"), (["字" * 100], 10, "x" * 10)])
def test_pack_rejects_invalid(blocks: list[str], limit: int, prefix: str) -> None:
    with pytest.raises(ValueError):
        pack_blocks(blocks, limit, prefix)


def test_strip_tags_decodes_and_preserves_linebreaks() -> None:
    assert strip_tags('<b>台灣 &amp; 晶片</b>\n<blockquote expandable>人工智慧&#128204;</blockquote>') == "台灣 & 晶片\n人工智慧📌"
    assert strip_tags("<b>未關閉 &amp; 測試\n<i>仍可閱讀") == "未關閉 & 測試\n仍可閱讀"
    assert strip_tags("<unsupported>文字</unsupported>") == "文字"
    assert strip_tags("&amp;lt;台灣&amp;gt;") == "&lt;台灣&gt;"
    assert strip_tags("<script>文字 &amp; 晶片</script>") == "文字 & 晶片"
