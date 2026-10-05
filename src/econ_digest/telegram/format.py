"""A strict subset of Telegram HTML, measured conservatively as source text."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re


_ALLOWED_TAGS = frozenset({"b", "i", "u", "s", "a", "code", "pre", "blockquote"})
_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|#[0-9]+);")
_TAG = re.compile(r"<(/?)([a-z]+)(\s[^<>]*?)?>", re.DOTALL)
_HREF = re.compile(r'''\s+href\s*=\s*(?:"([^"<>]*)"|'([^'<>]*)')\s*''')


def escape(text: str) -> str:
    """Escape a plain-text node; quotes are harmless outside attributes."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bold(text: str) -> str:
    return f"<b>{escape(text)}</b>"


def italic(text: str) -> str:
    return f"<i>{escape(text)}</i>"


def underline(text: str) -> str:
    return f"<u>{escape(text)}</u>"


def code(text: str) -> str:
    return f"<code>{escape(text)}</code>"


def link(url: str, text: str) -> str:
    attribute = escape(url).replace('"', "&quot;")
    return f'<a href="{attribute}">{escape(text)}</a>'


def blockquote(inner_html: str, expandable: bool = False) -> str:
    """Wrap already-formatted, validated HTML in a blockquote."""
    check_html(inner_html)
    attribute = " expandable" if expandable else ""
    return f"<blockquote{attribute}>{inner_html}</blockquote>"


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le", errors="surrogatepass")) // 2


@dataclass(frozen=True)
class _Token:
    raw: str
    kind: str = "text"
    tag: str = ""

    @property
    def units(self) -> int:
        return utf16_len(self.raw)


def _validate_entities(text: str) -> None:
    position = 0
    while (position := text.find("&", position)) >= 0:
        match = _ENTITY.match(text, position)
        if match is None:
            raise ValueError("Malformed HTML entity")
        position = match.end()


def _tokens(html: str) -> list[_Token]:
    tokens: list[_Token] = []
    stack: list[str] = []
    position = 0
    while position < len(html):
        character = html[position]
        if character == "<":
            match = _TAG.match(html, position)
            if match is None:
                raise ValueError("Malformed HTML tag")
            closing, tag, attributes = match.groups()
            attributes = attributes or ""
            if tag not in _ALLOWED_TAGS:
                raise ValueError(f"Unsupported HTML tag: {tag}")
            if closing:
                if attributes.strip() or not stack or stack.pop() != tag:
                    raise ValueError("Unbalanced or improperly nested HTML tags")
            else:
                if tag == "a":
                    href = _HREF.fullmatch(attributes)
                    if href is None:
                        raise ValueError("Links require a single quoted href attribute")
                    _validate_entities(href.group(1) or href.group(2) or "")
                elif tag == "blockquote":
                    if attributes.strip() not in {"", "expandable"}:
                        raise ValueError("Unsupported blockquote attribute")
                elif attributes.strip():
                    raise ValueError(f"Attributes are not allowed on {tag}")
                stack.append(tag)
            tokens.append(_Token(match.group(), "close" if closing else "open", tag))
            position = match.end()
        elif character == "&":
            entity = _ENTITY.match(html, position)
            if entity is None:
                raise ValueError("Malformed HTML entity")
            tokens.append(_Token(entity.group()))
            position = entity.end()
        else:
            tokens.append(_Token(character))
            position += 1
    if stack:
        raise ValueError("Unclosed HTML tags")
    return tokens


def check_html(html: str) -> None:
    """Reject unsupported tags, attributes, bad nesting, and malformed entities."""
    _tokens(html)


def _closings(stack: list[_Token]) -> str:
    return "".join(f"</{token.tag}>" for token in reversed(stack))


def _split_html(html: str, limit: int, continuation_html: str = "") -> list[str]:
    if limit <= 0:
        raise ValueError("HTML message limit must be positive")
    tokens = _tokens(html)
    if utf16_len(html) <= limit:
        return [html]
    if utf16_len(continuation_html) >= limit:
        raise ValueError("Continuation prefix leaves no room for content")

    # Tags and entities are indivisible tokens; each boundary stores the open
    # elements so closing/reopening overhead participates in the size limit.
    units = [token.units for token in tokens]
    visible = [unescape(token.raw) if token.kind == "text" else "" for token in tokens]
    next_visible = [""] * len(tokens)
    following = ""
    for index in range(len(tokens) - 1, -1, -1):
        next_visible[index] = following
        if visible[index]:
            following = visible[index][0]

    chunks: list[str] = []
    start = 0
    open_stack: list[_Token] = []
    while start < len(tokens):
        header = continuation_html if chunks else ""
        reopening = "".join(token.raw for token in open_stack)
        size = utf16_len(header + reopening)
        stack = open_stack.copy()
        closing_size = utf16_len(_closings(stack))
        candidates: dict[int, tuple[int, list[_Token]]] = {}
        previous = ""
        has_text = False
        reached_end = False
        for index in range(start, len(tokens)):
            token = tokens[index]
            size += units[index]
            if token.kind == "open":
                stack.append(token)
                closing_size += utf16_len(f"</{token.tag}>")
            elif token.kind == "close":
                stack.pop()
                closing_size -= utf16_len(f"</{token.tag}>")
            if size + closing_size > limit:
                break
            if token.kind == "text":
                has_text = True
                current = visible[index]
                priority = 3
                if previous.endswith("\n") and current == "\n":
                    priority = 0
                elif current == "\n":
                    priority = 1
                elif current in "。！？" or (
                    current in "!?." and (not next_visible[index] or next_visible[index].isspace())
                ):
                    priority = 2
                previous = current
                candidates[priority] = (index + 1, stack.copy())
            # Include closing tags following the last text without creating a
            # spurious empty chunk, and retain the latest hard boundary.
            if has_text or not stack:
                candidates[3] = (index + 1, stack.copy())
            if index + 1 == len(tokens):
                reached_end = True
        if reached_end:
            end, end_stack = len(tokens), []
        elif candidates:
            end, end_stack = candidates[min(candidates)]
        else:
            raise ValueError("HTML wrapper or indivisible entity exceeds the message limit")
        chunk = header + reopening + "".join(token.raw for token in tokens[start:end])
        chunks.append(chunk + _closings(end_stack))
        start, open_stack = end, end_stack
    return chunks


def split_html(html: str, limit: int = 4000) -> list[str]:
    """Split source HTML and preserve valid formatting in every message."""
    return _split_html(html, limit)


def pack_blocks(
    blocks: list[str], limit: int = 4000, continuation_prefix: str = "（續）\n"
) -> list[str]:
    """Greedily pack blocks; the continuation prefix is treated as plain text."""
    if limit <= 0:
        raise ValueError("HTML message limit must be positive")
    messages: list[str] = []
    pending = ""
    for block in blocks:
        check_html(block)
        if not block:
            continue
        if utf16_len(block) > limit:
            if pending:
                messages.append(pending)
                pending = ""
            pieces = _split_html(block, limit, escape(continuation_prefix))
            messages.extend(pieces[:-1])
            pending = pieces[-1]
        else:
            combined = pending + "\n\n" + block if pending else block
            if utf16_len(combined) <= limit:
                pending = combined
            else:
                messages.append(pending)
                pending = block
    if pending:
        messages.append(pending)
    return messages


def strip_tags(html: str) -> str:
    """Return decoded text while preserving the original line breaks."""
    # The fallback must also handle the malformed markup Telegram rejected.
    class TextParser(HTMLParser):
        CDATA_CONTENT_ELEMENTS: tuple[str, ...] = ()

        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

    parser = TextParser()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)
