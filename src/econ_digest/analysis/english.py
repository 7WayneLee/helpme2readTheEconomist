"""Learner-oriented selection and a faithful article study guide."""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..models import Article, Classification, Issue
from .prompts import Unit, make_unit, numbered_text, prompt_json
from .validation import text, validate_guide

ENGLISH_KINDS = {"article", "leader", "briefing", "column", "by_invitation", "obituary"}


def english_candidates(issue: Issue, config: Config) -> list[Article]:
    return [article for article in issue.articles if article.kind in ENGLISH_KINDS
            and config.english.min_words <= article.word_count <= config.english.max_words]


def pick_unit(issue: Issue, classifications: dict[str, Classification], config: Config,
              history: list[dict[str, Any]] | None = None, *,
              exclude_ids: frozenset[str] = frozenset()) -> Unit | None:
    candidates = [article for article in english_candidates(issue, config) if article.id not in exclude_ids]
    if not candidates:
        return None
    ids = {article.id for article in candidates}

    def validate(data: dict[str, Any]) -> None:
        if not isinstance(data.get("article_id"), str) or data["article_id"] not in ids:
            raise ValueError("article_id must identify an eligible English candidate")
        text(data.get("reason_zh"), "reason_zh")

    unit = make_unit("english_pick", issue.issue_date, sorted(ids), config.llm.models.english, validate,
                     level=config.english.level, candidates=prompt_json([
                         {"id": article.id, "section": article.section, "kind": article.kind,
                          "fly_title": article.fly_title, "title": article.title, "rubric": article.rubric,
                          "word_count": article.word_count, "first_paragraph": article.paragraphs[0] if article.paragraphs else "",
                          "taiwan_level": classifications[article.id].taiwan_level} for article in candidates]),
                     history=prompt_json([{key: item.get(key, "") for key in ("section", "kind", "title")}
                                          for item in (history or [])[-8:]]))
    if unit.prompt_bytes > 90_000:
        raise ValueError("english_pick exceeds 90,000 prompt bytes")
    return unit


def guide_unit(issue: Issue, article: Article, config: Config) -> Unit:
    unit = make_unit("english_guide", issue.issue_date, [article.id], config.llm.models.english,
                     lambda data: validate_guide(data, article, config.english), level=config.english.level,
                     vocab_count=config.english.vocab_count, phrase_count=config.english.phrase_count,
                     article=prompt_json({"article_id": article.id, "title": article.title,
                                          "rubric": article.rubric, "text": numbered_text(article.paragraphs)}))
    if unit.prompt_bytes > 90_000:
        raise ValueError("english_guide exceeds 90,000 prompt bytes")
    return unit
