from __future__ import annotations

from pathlib import Path

import pytest

from econ_digest.analysis.classification import (apply_tiers, classify_units, fallback_classification,
                                                  fixed_classification, pair_unit, validate_classification, validate_pairs)
from econ_digest.config import Config, load_config, ConfigError
from econ_digest.models import Classification

from conftest import article, issue


def valid(identifier: str = "a1") -> dict:
    return {"article_id": identifier, "taiwan_level": 3, "mentions_taiwan": False,
            "taiwan_link": "（推論）晶片管制牽動台灣供應鏈。", "category": "tech", "title_zh": "晶片管制擴大"}


def test_classification_batches_and_context(analysis_config: Config) -> None:
    articles = [article(f"a{i}", paragraphs=["Taiwan and chips. " * 20]) for i in range(45)]
    units = classify_units(issue(articles), analysis_config)
    assert [len(unit.article_ids) for unit in units] == [20, 20, 5]
    assert all(unit.prompt_bytes <= 60_000 for unit in units)
    assert '"strong_terms":["Taiwan"]' in units[0].prompt
    assert '"weak_terms":["chips"]' in units[0].prompt
    assert "台灣是報導的主要主題" in units[0].prompt
    assert "兩岸共享文化傳承" in units[0].prompt and "印度占星投資" in units[0].prompt


@pytest.mark.parametrize("items", [[], [valid(), valid()], [valid("unknown")]])
def test_classification_ids(items: list[dict]) -> None:
    with pytest.raises(ValueError, match="exactly once"):
        validate_classification({"articles": items}, {"a1"})


@pytest.mark.parametrize("key,value", [("taiwan_level", True), ("taiwan_level", 4), ("category", "unknown"),
                                       ("taiwan_link", None), ("title_zh", ""), ("mentions_taiwan", 1)])
def test_classification_fields(key: str, value: object) -> None:
    item = valid()
    item[key] = value
    with pytest.raises(ValueError):
        validate_classification({"articles": [item]}, {"a1"})


def test_passing_mention_and_implicit_relevance() -> None:
    implicit = valid()
    validate_classification({"articles": [implicit]}, {"a1"})
    passing = {**valid(), "taiwan_level": 0, "mentions_taiwan": True, "taiwan_link": None}
    validate_classification({"articles": [passing]}, {"a1"})


@pytest.mark.parametrize("companions", [["a1", "a1"], ["l1", None], ["absent", None]])
def test_pair_validation(companions: list[str | None]) -> None:
    data = {"pairs": [{"article_id": f"l{i}", "companion_id": companion} for i, companion in enumerate(companions, 1)]}
    with pytest.raises(ValueError):
        validate_pairs(data, {"l1", "l2"}, {"a1", "a2"})


def test_pair_and_companion_minimums(analysis_config: Config) -> None:
    articles = [article("l1", kind="leader", cover=True), article("l2", kind="leader"), article("a1"), article("a2")]
    classifications = {a.id: Classification(a.id, 0, False, None, "culture", "測試") for a in articles}
    classifications["l1"].companion_id = "a1"
    classifications["l2"].companion_id = "a2"
    apply_tiers(articles, classifications, analysis_config.tiers)
    assert [classifications[a.id].tier for a in articles] == ["merged", "merged", "B", "C"]
    classifications["a1"].taiwan_level = 1
    apply_tiers(articles, classifications, analysis_config.tiers)
    assert classifications["a1"].tier == "A"
    unit = pair_unit(issue(articles), analysis_config)
    assert unit is not None and len(unit.article_ids) == 4


@pytest.mark.parametrize("kind,tier", [("cartoon", "skip"), ("indicators", "skip"),
                                        ("world_politics", "brief"), ("world_business", "brief")])
def test_fixed_items(kind: str, tier: str) -> None:
    classification = fixed_classification(article("a1", kind=kind))
    assert classification is not None and classification.tier == tier and classification.taiwan_level == 0


@pytest.mark.parametrize("section,category", [("China", "intl.china"), ("Business", "finance"),
                                               ("United States", "intl.us"), ("Science & technology", "science")])
def test_fallback_signals(section: str, category: str) -> None:
    result = fallback_classification(article("a1", section=section, paragraphs=["TSMC is in Taiwan."]))
    assert result.category == category and result.taiwan_level == 3 and result.mentions_taiwan


def test_companion_config_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[tiers]\ncover_companion_min = "A"\nleader_companion_min = "B"\n')
    assert load_config(path).tiers.cover_companion_min == "A"
    path.write_text('[tiers]\ncover_companion_min = "skip"\n')
    with pytest.raises(ConfigError, match="cover_companion_min"):
        load_config(path)
