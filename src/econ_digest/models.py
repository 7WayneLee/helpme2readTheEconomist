"""Shared data contracts and atomic UTF-8 JSON persistence."""

from __future__ import annotations

import json
import os
import tempfile
import types
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

T = TypeVar("T")


def _encode(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _decode(annotation: Any, value: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        for candidate in args:
            if candidate is not type(None):
                return _decode(candidate, value)
    if is_dataclass(annotation):
        hints = get_type_hints(annotation)
        return annotation(**{
            f.name: _decode(hints[f.name], value[f.name])
            for f in fields(annotation) if f.name in value
        })
    if origin is list:
        return [_decode(args[0], item) for item in value]
    if origin is dict:
        return {_decode(args[0], key): _decode(args[1], item) for key, item in value.items()}
    return value


class JsonModel:
    def to_dict(self) -> dict[str, Any]:
        return _encode(self)

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        return _decode(cls, data)


def save_json(path: str | Path, obj: Any) -> None:
    """Replace a JSON file only after its complete contents reach disk."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(_encode(obj), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_json(path: str | Path, cls: type[T]) -> T:
    with Path(path).open(encoding="utf-8") as stream:
        return _decode(cls, json.load(stream))


@dataclass
class Article(JsonModel):
    id: str
    order: int
    section: str
    fly_title: str | None
    title: str
    rubric: str | None
    date_published: str | None
    paragraphs: list[str]
    word_count: int
    kind: str
    is_cover: bool = False


@dataclass
class Issue(JsonModel):
    issue_date: str
    source_url: str
    fetched_at: str
    articles: list[Article]


@dataclass
class TaiwanSignals(JsonModel):
    strong_terms: list[str]
    weak_terms: list[str]
    mention_count: int
    snippets: list[str]


@dataclass
class Source(JsonModel):
    outlet: str
    date: str
    title: str
    url: str


@dataclass
class Classification(JsonModel):
    article_id: str
    taiwan_level: int
    mentions_taiwan: bool
    taiwan_link: str | None
    category: str
    title_zh: str
    companion_id: str | None = None
    tier: str = ""
    sources: list[Source] = field(default_factory=list)


@dataclass
class Quote(JsonModel):
    en: str
    zh: str


@dataclass
class Argument(JsonModel):
    claim: str
    evidence: list[str]
    counterpoints: list[str]
    conclusion: str


@dataclass
class ArticleSummary(JsonModel):
    article_id: str
    tier: str
    headline_zh: str
    summary_zh: str | None = None
    key_points: list[str] = field(default_factory=list)
    background: str | None = None
    structure: list[str] = field(default_factory=list)
    argument: Argument | None = None
    key_data: list[str] = field(default_factory=list)
    quotes: list[Quote] = field(default_factory=list)
    stance: str | None = None
    taiwan_implications: list[str] = field(default_factory=list)
    further_questions: list[str] = field(default_factory=list)
    leader_stance: str | None = None
    model: str | None = None
    sources: list[Source] = field(default_factory=list)


@dataclass
class BriefItem(JsonModel):
    text_zh: str
    taiwan_related: bool = False


@dataclass
class WeekBrief(JsonModel):
    politics: list[BriefItem]
    business: list[BriefItem]


@dataclass
class VocabItem(JsonModel):
    word: str
    pos: str
    meaning_zh: str
    example_en: str
    note_zh: str | None = None


@dataclass
class PhraseItem(JsonModel):
    phrase: str
    meaning_zh: str
    example_en: str


@dataclass
class SentenceAnalysis(JsonModel):
    sentence_en: str
    breakdown_zh: str
    translation_zh: str


@dataclass
class QuizItem(JsonModel):
    question: str
    answer: str


@dataclass
class EnglishPick(JsonModel):
    article_id: str
    reason_zh: str
    cefr: str
    word_count: int
    reading_minutes: int
    pre_reading_zh: str
    vocabulary: list[VocabItem]
    phrases: list[PhraseItem]
    sentences: list[SentenceAnalysis]
    writing_notes_zh: list[str]
    quiz: list[QuizItem]


@dataclass
class LLMCallStat(JsonModel):
    stage: str
    model: str
    ok: bool
    total_tokens: int
    duration_seconds: float


@dataclass
class Digest(JsonModel):
    issue_date: str
    generated_at: str
    issue: Issue
    classifications: dict[str, Classification]
    summaries: dict[str, ArticleSummary]
    week_brief: WeekBrief | None
    english: EnglishPick | None
    llm_calls: list[LLMCallStat] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    focus_ids: list[str] = field(default_factory=list)
    fact_alerts: list[dict] = field(default_factory=list)
