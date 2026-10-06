"""Offline concept hints from a curated NAER terminology subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

MAX_HINT_TERMS = 15
MAX_HINT_BYTES = 900
_COMMON = frozenset("bank business capital cost demand energy exchange finance health interest law market "
                    "model money policy power price public rate risk security state stock supply system "
                    "tax technology trade value war work".split())
_LABEL = "譯名參考（國家教育研究院樂詞網）："
_GUIDANCE = "僅供概念譯名參考，須依原文語境選用，不得據此新增事實；人名、地名仍依中央社慣例。"


@dataclass(frozen=True)
class Term:
    english: str
    chinese: str


def _order(term: Term) -> tuple[int, int, str]:
    return (-len(term.english.split()), -len(term.english), term.english.casefold())


@lru_cache(maxsize=4)
def _parse_terms(text: str) -> tuple[Term, ...]:
    translations: dict[str, set[str]] = {}
    for row in text.splitlines():
        if not row.strip() or row.lstrip().startswith("#"):
            continue
        columns = row.split("\t")
        if len(columns) < 2:
            continue
        english, chinese = (" ".join(value.split()) for value in columns[:2])
        english = english.casefold()
        if (len(english) < 4 or english in _COMMON
                or not re.fullmatch(r"[a-z][a-z0-9]*(?:[ '-][a-z0-9]+)*", english)
                or not re.fullmatch(r"[\u3400-\u9fff]+", chinese)):
            continue
        translations.setdefault(english, set()).add(chinese)
    return tuple(sorted((Term(english, next(iter(chinese)))
                         for english, chinese in translations.items() if len(chinese) == 1), key=_order))


def load_terms(path: Path | None = None) -> tuple[Term, ...]:
    """A missing/unreadable table is optional; no downloads or fallback queries."""
    try:
        table = path if path is not None else files(__package__).joinpath("terms.tsv")
        return _parse_terms(table.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError):
        return ()


@lru_cache(maxsize=4)
def _patterns(terms: tuple[Term, ...]) -> tuple[tuple[Term, re.Pattern[str]], ...]:
    return tuple((term, re.compile(r"(?<!\w)" + r"\s+".join(
        re.escape(word) for word in term.english.split()) + r"(?!\w)", re.I))
                 for term in sorted(set(terms), key=_order))


def matching_terms(text: str, terms: tuple[Term, ...] | None = None) -> tuple[Term, ...]:
    """Prefer specific phrases; a nested shorter match cannot consume a slot."""
    selected: list[Term] = []
    occupied: list[tuple[int, int]] = []
    for term, pattern in _patterns(load_terms() if terms is None else terms):
        matches = [match.span() for match in pattern.finditer(text)
                   if not any(match.start() < end and match.end() > start for start, end in occupied)]
        if matches:
            selected.append(term)
            occupied.extend(matches)
            if len(selected) == MAX_HINT_TERMS:
                break
    return tuple(selected)


def terminology_hint(text: str, terms: tuple[Term, ...] | None = None) -> str:
    entries: list[str] = []
    for term in matching_terms(text, terms):
        entry = f"{term.english} → {term.chinese}"
        candidate = _LABEL + "；".join([*entries, entry]) + "\n" + _GUIDANCE
        if len(candidate.encode("utf-8")) <= MAX_HINT_BYTES:
            entries.append(entry)
    return _LABEL + "；".join(entries) + "\n" + _GUIDANCE if entries else ""
