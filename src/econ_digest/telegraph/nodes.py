"""Telegraph's DOM subset and its exact UTF-8 JSON size."""

from __future__ import annotations

import json
from typing import TypeAlias

Node: TypeAlias = str | dict[str, object]
ALLOWED_TAGS = frozenset({
    "a", "aside", "b", "blockquote", "br", "code", "em", "figcaption", "figure",
    "h3", "h4", "hr", "i", "iframe", "img", "li", "ol", "p", "pre", "s",
    "strong", "u", "ul", "video",
})


def node(tag: str, *children: Node, **attrs: str) -> Node:
    result: dict[str, object] = {"tag": tag, "children": list(children)}
    if attrs:
        result["attrs"] = attrs
    return result


def validate_nodes(nodes: list[Node]) -> None:
    if not isinstance(nodes, list):
        raise ValueError("Telegraph 內容必須是 Node 陣列")
    for item in nodes:
        if isinstance(item, str):
            continue
        if not isinstance(item, dict) or set(item) - {"tag", "attrs", "children"}:
            raise ValueError("Telegraph Node 格式無效")
        tag = item.get("tag")
        if not isinstance(tag, str) or tag not in ALLOWED_TAGS:
            raise ValueError("Telegraph Node 包含不支援的標籤")
        attrs = item.get("attrs", {})
        if (not isinstance(attrs, dict) or set(attrs) - {"href", "src"}
                or any(not isinstance(value, str) for value in attrs.values())):
            raise ValueError("Telegraph Node 屬性無效")
        children = item.get("children", [])
        validate_nodes(children)  # type: ignore[arg-type]


def content_json(nodes: list[Node]) -> str:
    validate_nodes(nodes)
    return json.dumps(nodes, ensure_ascii=False)


def content_size(nodes: list[Node]) -> int:
    return len(content_json(nodes).encode("utf-8"))
