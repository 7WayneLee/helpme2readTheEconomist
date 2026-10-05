"""One Chinese headline per world-this-week paragraph."""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..models import Issue
from .prompts import Unit, make_unit, prompt_json
from .validation import chinese_length, text


def brief_inputs(issue: Issue) -> dict[str, list[str]]:
    return {name: [paragraph for article in issue.articles if article.kind == f"world_{name}"
                   for paragraph in article.paragraphs] for name in ("politics", "business")}


def validate_brief(data: dict[str, Any], inputs: dict[str, list[str]]) -> None:
    for name, paragraphs in inputs.items():
        items = data.get(name)
        if not isinstance(items, list) or len(items) != len(paragraphs):
            raise ValueError(f"{name} requires exactly {len(paragraphs)} items in input order")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{name} items must be objects")
            if chinese_length(text(item.get("text_zh"), "text_zh")) > 80:
                raise ValueError("brief text_zh must be at most 80 Chinese characters")
            if type(item.get("taiwan_related")) is not bool:
                raise ValueError("taiwan_related must be a boolean")


def brief_unit(issue: Issue, config: Config) -> Unit | None:
    inputs = brief_inputs(issue)
    if not any(inputs.values()):
        return None
    unit = make_unit("brief", issue.issue_date, [article.id for article in issue.articles
                                               if article.kind in {"world_politics", "world_business"}],
                     config.llm.models.brief, lambda data: validate_brief(data, inputs),
                     items=prompt_json(inputs))
    if unit.prompt_bytes > 90_000:
        raise ValueError("brief exceeds 90,000 prompt bytes")
    return unit
