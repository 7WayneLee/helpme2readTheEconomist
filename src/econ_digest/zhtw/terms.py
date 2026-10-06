"""Offline concept hints from a curated NAER terminology subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from heapq import merge
from importlib.resources import files
from importlib.resources.abc import Traversable
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


def _read_terms(table: Path | Traversable) -> tuple[Term, ...]:
    try:
        return _parse_terms(table.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError):
        return ()


@lru_cache(maxsize=1)
def _default_terms() -> tuple[Term, ...]:
    try:
        return _read_terms(files(__package__).joinpath("terms.tsv"))
    except (OSError, UnicodeError):
        return ()


def load_terms(path: Path | None = None) -> tuple[Term, ...]:
    """Read the packaged table once; explicit paths remain refreshable/optional."""
    return _default_terms() if path is None else _read_terms(path)


@lru_cache(maxsize=4)
def _patterns(terms: tuple[Term, ...]) -> tuple[
    tuple[Term, ...], re.Pattern[str], tuple[tuple[str, tuple[int, ...]], ...]
]:
    ordered = tuple(sorted(set(terms), key=_order))
    expressions: list[str] = []
    initials: dict[str, list[int]] = {}
    for index, term in enumerate(ordered):
        words = term.english.split()
        expressions.append(r"\s+".join(re.escape(word) for word in words) + r"(?!\w)")
        initials.setdefault(words[0][0] if words else "", []).append(index)

    # The guard finds any term in priority order. Optional lookaheads then keep
    # *all* matches at that start, including shorter prefixes: the longest one
    # may itself be blocked by a higher-priority phrase starting elsewhere.
    branches: list[str] = []
    buckets: list[tuple[str, tuple[int, ...]]] = []
    for initial, indices in initials.items():
        name = f"b{len(buckets)}"
        guard = f"(?={re.escape(initial)})" if initial else ""
        captures = "".join(f"(?:(?=(?P<t{i}>{expressions[i]})))?" for i in indices)
        branches.append(f"(?P<{name}>{guard}{captures})?")
        buckets.append((name, tuple(indices)))
    pattern = re.compile(r"(?<!\w)(?=(?:" + "|".join(expressions or [r"(?!)"])
                         + "))" + "".join(branches), re.I)
    return ordered, pattern, tuple(buckets)


def _select_component(component: dict[int, list[tuple[int, int]]], selected: set[int],
                      cutoff: int) -> int:
    """Resolve a completed overlap component in the original term priority."""
    occupied: list[tuple[int, int]] = []
    for index in sorted(component):
        if index > cutoff:
            break
        available: list[tuple[int, int]] = []
        cursor = 0
        for start, end in component[index]:
            while cursor < len(occupied) and occupied[cursor][1] <= start:
                cursor += 1
            if cursor == len(occupied) or occupied[cursor][0] >= end:
                available.append((start, end))
        if available:
            selected.add(index)
            if len(selected) > MAX_HINT_TERMS:
                selected.remove(max(selected))
            if len(selected) == MAX_HINT_TERMS:
                cutoff = max(selected)
            # Both lists are already sorted and disjoint. A linear merge avoids
            # checking every occurrence against every earlier occupied span.
            occupied = list(merge(occupied, available))
    return cutoff


@lru_cache(maxsize=128)
def _matching_terms(text: str, terms: tuple[Term, ...]) -> tuple[Term, ...]:
    ordered, pattern, buckets = _patterns(terms)
    if not ordered:
        return ()
    selected: set[int] = set()
    cutoff = len(ordered) - 1
    limit = min(MAX_HINT_TERMS, len(ordered))
    component: dict[int, list[tuple[int, int]]] = {}
    component_end = -1
    last_ends = [-1] * len(ordered)
    for match in pattern.finditer(text):
        start = match.start()
        if component and start >= component_end:
            cutoff = _select_component(component, selected, cutoff)
            # No future match can change the result when every highest-priority
            # slot already has an unblocked occurrence in a completed component.
            if len(selected) == limit and cutoff == limit - 1:
                return tuple(ordered[i] for i in sorted(selected))
            component.clear()
            component_end = -1
        for name, indices in buckets:
            if match.start(name) == -1:
                continue
            for index in indices:
                if index > cutoff:
                    continue
                span = match.span(f"t{index}")
                if span[0] == -1 or start < last_ends[index]:
                    continue
                # Each original per-term finditer skipped self-overlapping
                # occurrences even when its previous match was later blocked.
                last_ends[index] = span[1]
                component.setdefault(index, []).append(span)
                component_end = max(component_end, span[1])
    _select_component(component, selected, cutoff)
    return tuple(ordered[i] for i in sorted(selected))


def matching_terms(text: str, terms: tuple[Term, ...] | None = None) -> tuple[Term, ...]:
    """Prefer specific phrases; a nested shorter match cannot consume a slot."""
    # Keeping the exact text as the LRU key also checks equality on hash
    # collisions; hashing alone could change prompt bytes for unrelated texts.
    return _matching_terms(text, load_terms() if terms is None else terms)


def terminology_hint(text: str, terms: tuple[Term, ...] | None = None) -> str:
    entries: list[str] = []
    for term in matching_terms(text, terms):
        entry = f"{term.english} → {term.chinese}"
        candidate = _LABEL + "；".join([*entries, entry]) + "\n" + _GUIDANCE
        if len(candidate.encode("utf-8")) <= MAX_HINT_BYTES:
            entries.append(entry)
    return _LABEL + "；".join(entries) + "\n" + _GUIDANCE if entries else ""
