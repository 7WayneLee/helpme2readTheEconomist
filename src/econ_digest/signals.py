"""Deterministic Taiwan-related signals for LLM classification context."""

from __future__ import annotations

import re

from .models import Article, TaiwanSignals

STRONG_TERMS = (
    "Taiwan", "Taiwanese", "Taipei", "TSMC", "Taiwan Strait", "cross-strait",
    "Lai Ching-te", "William Lai", "Tsai Ing-wen", "Kuomintang", "KMT", "DPP",
    "Democratic Progressive Party", "Kinmen", "Matsu", "Penghu", "Kaohsiung",
    "Hsinchu", "Foxconn", "Hon Hai", "MediaTek", "UMC", "Pegatron", "Quanta",
    "Wistron", "Formosa",
)
WEAK_TERMS = (
    "semiconductor", "semiconductors", "chipmaker", "chipmakers", "chips", "Nvidia",
    "export controls", "PLA", "People's Liberation Army", "South China Sea",
    "first island chain", "reunification", "blockade", "invasion", "Philippines", "Okinawa",
)
_ACRONYMS = {"TSMC", "KMT", "DPP", "UMC", "PLA"}


def _pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    expressions: list[str] = []
    # A phrase such as Taiwan Strait counts once, rather than counting Taiwan twice.
    for term in sorted(terms, key=len, reverse=True):
        escaped = re.escape(term).replace("'", "['’]")
        expressions.append(escaped if term in _ACRONYMS else f"(?i:{escaped})")
    return re.compile(r"(?<!\w)(?:" + "|".join(expressions) + r")(?!\w)")


_STRONG_PATTERN = _pattern(STRONG_TERMS)
_WEAK_PATTERN = _pattern(WEAK_TERMS)
_CANONICAL = {term.casefold(): term for term in STRONG_TERMS + WEAK_TERMS}


def _canonical(match: re.Match[str]) -> str:
    return _CANONICAL[match.group().replace("’", "'").casefold()]


def _snippet(sentence: str, match: re.Match[str]) -> str:
    if len(sentence) <= 300:
        return sentence
    start = max(0, match.start() - (298 - len(match.group())) // 2)
    start = min(start, len(sentence) - 298)
    end = start + 298
    return ("…" if start else "") + sentence[start:end].strip() + ("…" if end < len(sentence) else "")


def find_taiwan_signals(article: Article) -> TaiwanSignals:
    blocks = [article.title, article.rubric or "", *article.paragraphs]
    text = "\n".join(blocks)
    strong = list(_STRONG_PATTERN.finditer(text))
    weak = list(_WEAK_PATTERN.finditer(text))
    snippets: list[str] = []
    for block in blocks:
        for sentence in re.split(r"(?<=[.!?。！？])\s+", block):
            sentence = sentence.strip()
            match = _STRONG_PATTERN.search(sentence)
            if match and sentence:
                snippet = _snippet(sentence, match)
                if snippet not in snippets:
                    snippets.append(snippet)
            if len(snippets) == 5:
                break
        if len(snippets) == 5:
            break
    return TaiwanSignals(
        strong_terms=list(dict.fromkeys(_canonical(match) for match in strong)),
        weak_terms=list(dict.fromkeys(_canonical(match) for match in weak)),
        mention_count=len(strong), snippets=snippets,
    )
