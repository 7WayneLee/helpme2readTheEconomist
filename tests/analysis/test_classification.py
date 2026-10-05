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


@pytest.mark.parametrize('body,kind,level,link', [
    ('The presidential hotline was established in 1998 after the Taiwan Strait crisis of 1996.',
     'substantive', 3, '原文回顧 1996 年台海危機後，美中在 1998 年建立元首熱線。'),
    ('Taiwan changed its industrial policy. Its experience provides a comparison for this reform.',
     'substantive', 3, '原文以台灣產業政策作為改革的比較。'),
    ('The new policy requires Taiwan to take part in the talks.',
     'substantive', 2, '原文指出新政策要求台灣參與談判。'),
    ('The party sends messages to Taiwan about a shared cultural heritage.',
     'substantive', 3, '原文報導中共向台灣傳達共享文化傳承的政治訊息。'),
    ('The survey covered India, Taiwan, Japan and France.',
     'incidental', 0, None),
    ('A Taiwanese study is cited as an example in a report on Indian financial astrology.',
     'incidental', 0, None),
    ('A poll measures attitudes towards China across Latin America.',
     'none', 0, None),
    ('A new export policy restricts chip sales by all firms to China.',
     'none', 3, '（推論）原文的晶片出口限制適用所有廠商，台灣廠商對中國的銷售也在管制範圍。'),
])
def test_article_discussion_and_incidental_mentions(analysis_config, body, kind, level, link):
    source = issue([article('a1', paragraphs=[body])])
    unit = classify_units(source, analysis_config)[0]
    item = {**valid(), 'taiwan_level': level, 'mentions_taiwan': kind != 'none',
            'taiwan_mention_kind': kind, 'taiwan_evidence': body if kind != 'none' or level else None,
            'taiwan_link': link}
    unit.validate({'articles': [item]})
    if kind == 'substantive':
        with pytest.raises(ValueError, match='Substantive'):
            unit.validate({'articles': [{**item, 'taiwan_level': 0, 'taiwan_link': None}]})
        with pytest.raises(ValueError, match='without speculation'):
            unit.validate({'articles': [{**item, 'taiwan_link': '（推論）' + link}]})
    if kind == 'incidental':
        with pytest.raises(ValueError, match='incidental'):
            unit.validate({'articles': [{**item, 'taiwan_level': 3, 'taiwan_link': '不能強拉關聯。'}]})
    if kind != 'none' or level:
        with pytest.raises(ValueError, match='verbatim'):
            unit.validate({'articles': [{**item, 'taiwan_evidence': 'An invented source sentence.'}]})


def test_source_assessment_required_and_mentions_consistent(analysis_config):
    unit = classify_units(issue([article('a1')]), analysis_config)[0]
    with pytest.raises(ValueError, match='taiwan_mention_kind'):
        unit.validate({'articles': [valid()]})
    with pytest.raises(ValueError, match='must agree'):
        unit.validate({'articles': [{**valid(), 'taiwan_mention_kind': 'substantive'}]})


@pytest.mark.parametrize('kind', [None, [], {}])
def test_malformed_source_assessment_is_repairable(analysis_config, kind):
    unit = classify_units(issue([article('a1')]), analysis_config)[0]
    with pytest.raises(ValueError, match='taiwan_mention_kind'):
        unit.validate({'articles': [{**valid(), 'taiwan_mention_kind': kind}]})


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
