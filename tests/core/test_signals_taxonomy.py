from __future__ import annotations

from dataclasses import replace

import pytest

from econ_digest.config import TiersConfig
from econ_digest.models import Article
from econ_digest.signals import find_taiwan_signals
from econ_digest.taxonomy import COLUMN_NAMES, assign_tier, derive_kind


def test_strong_and_weak_signals_in_first_seen_order(synthetic_article: Article) -> None:
    article = replace(synthetic_article, title="Taipei and Taiwan", rubric="TSMC semiconductor chips",
                      paragraphs=["Taiwanese visitors crossed the Taiwan Strait. TAIWAN and TSMC appeared again."])
    signals = find_taiwan_signals(article)
    assert signals.strong_terms == ["Taipei", "Taiwan", "TSMC", "Taiwanese", "Taiwan Strait"]
    assert signals.weak_terms == ["semiconductor", "chips"]
    assert signals.mention_count == 7
    assert signals.snippets[0] == article.title


def test_case_rules_boundaries_and_typographic_apostrophe(synthetic_article: Article) -> None:
    article = replace(synthetic_article, title="tsmc kmt dpp umc Taiwaneseish taiwan",
                      rubric=None, paragraphs=["TSMC KMT DPP UMC PLA pla People’s Liberation Army."])
    signals = find_taiwan_signals(article)
    assert signals.strong_terms == ["Taiwan", "TSMC", "KMT", "DPP", "UMC"]
    assert signals.mention_count == 5
    assert signals.weak_terms == ["PLA", "People's Liberation Army"]


def test_snippet_limit_and_match_centering(synthetic_article: Article) -> None:
    long_sentence = "before " * 80 + "Hsinchu " + "after " * 80 + "."
    article = replace(synthetic_article, title="Synthetic", rubric=None,
                      paragraphs=[long_sentence] + [f"Taiwan invented sentence {i}." for i in range(10)])
    signals = find_taiwan_signals(article)
    assert len(signals.snippets) == 5
    assert all(len(snippet) <= 300 for snippet in signals.snippets)
    assert "Hsinchu" in signals.snippets[0]


def test_no_strong_terms_produces_no_snippets(synthetic_article: Article) -> None:
    article = replace(synthetic_article, title="Synthetic chips", rubric=None, paragraphs=["Nvidia faces a blockade."])
    signals = find_taiwan_signals(article)
    assert not signals.strong_terms and not signals.snippets
    assert signals.mention_count == 0
    assert signals.weak_terms == ["chips", "Nvidia", "blockade"]


@pytest.mark.parametrize("kind,level,category,companion,expected", [
    ("cartoon", 1, "intl.us", False, "skip"),
    ("indicators", 1, "intl.us", False, "skip"),
    ("world_politics", 1, "intl.us", False, "brief"),
    ("world_business", 1, "intl.us", False, "brief"),
    ("leader", 1, "intl.us", True, "merged"),
    ("leader", 1, "intl.us", False, "A"),
    ("letters", 1, "intl.us", False, "E"),
    ("obituary", 2, "culture", False, "E"),
    ("article", 1, "culture", False, "A"),
    ("article", 2, "culture", False, "B"),
    ("article", 3, "culture", False, "C"),
    ("article", 0, "intl.us", False, "C"),
    ("article", 0, "intl.asia", False, "D"),
    ("article", 0, "culture", False, "E"),
    ("briefing", 0, "culture", False, "C"),
    ("briefing", 1, "culture", False, "A"),
    ("briefing", 3, "culture", False, "C"),
    ("by_invitation", 0, "tech", False, "D"),
])
def test_assign_tier_precedence(kind: str, level: int, category: str, companion: bool, expected: str) -> None:
    assert assign_tier(kind, level, category, companion, TiersConfig()) == expected


def test_forced_tier_precedes_minimum() -> None:
    config = TiersConfig(force_tier_by_kind={"briefing": "E"}, min_tier_by_kind={"briefing": "A"})
    assert assign_tier("briefing", 1, "intl.us", False, config) == "E"


@pytest.mark.parametrize("section,title,fly,expected", [
    ("The world this week", "Politics", None, "world_politics"),
    ("The world this week", "Business", None, "world_business"),
    ("The world this week", "Cartoon: Synthetic", None, "cartoon"),
    ("The world this week", "Anything else", None, "cartoon"),
    ("Leaders", "Synthetic", "Chaguan", "leader"),
    ("Briefing", "Synthetic", None, "briefing"),
    ("By Invitation", "Synthetic", None, "by_invitation"),
    ("Letters", "Synthetic", None, "letters"),
    ("Obituary", "Synthetic", None, "obituary"),
    ("Economic & financial indicators", "Synthetic", None, "indicators"),
    ("Technology Quarterly", "Synthetic", None, "article"),
    ("1843", "Synthetic", None, "article"),
] + [("Synthetic section", "Title", name.swapcase(), "column") for name in COLUMN_NAMES])
def test_derive_kind(section: str, title: str, fly: str | None, expected: str) -> None:
    assert derive_kind(section, title, fly) == expected
