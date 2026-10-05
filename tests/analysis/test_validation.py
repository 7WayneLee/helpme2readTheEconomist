from __future__ import annotations

import pytest

from econ_digest.analysis.brief import validate_brief
from econ_digest.analysis.validation import source_contains, validate_guide, validate_summary
from econ_digest.config import Config
from conftest import article, guide, summary


@pytest.mark.parametrize("tier", list("ABCDE"))
def test_valid_summary_each_tier(tier: str) -> None:
    validate_summary(summary("a1", tier), article("a1"), tier)


@pytest.mark.parametrize("tier,field", [("A", "background"), ("A", "structure"), ("A", "argument"),
                                       ("A", "key_data"), ("A", "stance"), ("A", "taiwan_implications"),
                                       ("A", "further_questions"), ("B", "key_points"), ("B", "argument"),
                                       ("B", "taiwan_implications"), ("C", "key_points"), ("D", "summary_zh"),
                                       ("E", "headline_zh")])
def test_missing_summary_fields(tier: str, field: str) -> None:
    data = summary("a1", tier)
    del data[field]
    with pytest.raises(ValueError):
        validate_summary(data, article("a1"), tier)


@pytest.mark.parametrize("tier,field,value", [("A", "structure", ["第 99 段：不存在"] * 4),
                                             ("B", "key_points", ["短"] * 4),
                                             ("C", "key_points", ["短"] * 2),
                                             ("D", "summary_zh", "只有一句。"),
                                             ("E", "headline_zh", "標題")])
def test_summary_depth_validation(tier: str, field: str, value: object) -> None:
    data = summary("a1", tier)
    data[field] = value
    with pytest.raises(ValueError):
        validate_summary(data, article("a1"), tier)


def test_drop_fabricated_quotes_before_repair() -> None:
    data = summary("a1", "A")
    data["quotes"].append({"en": "A completely invented quote.", "zh": "虛構引文。"})
    validate_summary(data, article("a1"), "A")
    assert len(data["quotes"]) == 2
    data["quotes"][0]["en"] = "Another invented quote."
    with pytest.raises(ValueError, match="invented quotes"):
        validate_summary(data, article("a1"), "A")
    assert len(data["quotes"]) == 1


def test_english_normalised_quotes_and_trimmed_examples() -> None:
    source = article("a1", paragraphs=['“Costs” rose—quickly,  but firms’ resolve held. A second sentence.'])
    assert source_contains(source, '"Costs" rose-quickly, but firms\' resolve held.')
    assert source_contains(source, '"Costs" rose…resolve held.', trimmed=True)
    assert not source_contains(source, "resolve held…Costs", trimmed=True)


def test_leader_stance_required() -> None:
    with pytest.raises(ValueError, match="leader_stance"):
        validate_summary(summary("a1", "C"), article("a1"), "C", leader=True)
    validate_summary(summary("a1", "C", leader=True), article("a1"), "C", leader=True)


def test_brief_counts() -> None:
    data = {"politics": [{"text_zh": "一則新聞。", "taiwan_related": True}], "business": []}
    validate_brief(data, {"politics": ["Input"], "business": []})
    with pytest.raises(ValueError, match="exactly 2"):
        validate_brief(data, {"politics": ["One", "Two"], "business": []})


def test_guide_validation(analysis_config: Config) -> None:
    validate_guide(guide(), article("a1"), analysis_config.english)


@pytest.mark.parametrize("field", ["vocabulary", "phrases", "sentences", "quiz"])
def test_guide_counts(field: str, analysis_config: Config) -> None:
    data = guide()
    data[field] = []
    with pytest.raises(ValueError):
        validate_guide(data, article("a1"), analysis_config.english)


@pytest.mark.parametrize("field,en_key", [("vocabulary", "example_en"), ("phrases", "example_en"), ("sentences", "sentence_en")])
def test_guide_fabricated_examples(field: str, en_key: str, analysis_config: Config) -> None:
    data = guide()
    data[field][0][en_key] = "This never appears in the source."
    with pytest.raises(ValueError, match="verbatim"):
        validate_guide(data, article("a1"), analysis_config.english)


def test_guide_quiz_cites_valid_paragraph(analysis_config: Config) -> None:
    data = guide()
    data["quiz"][0]["answer"] = "第 99 段是答案。"
    with pytest.raises(ValueError, match="valid paragraph"):
        validate_guide(data, article("a1"), analysis_config.english)


@pytest.mark.parametrize("lemma,form,pos,note", [
    ("shun", "shunned", "v.", "原文為過去式 shunned"),
    ("collide", "collided", "v.", "原文為過去式 collided"),
    ("ShUn", "SHUNNED", "v.", "原文為過去式 SHUNNED"),
    ("policy", "policies", "n.", "原文為複數 policies"),
    ("study", "studied", "v.", "原文為過去式 studied"),
    ("rise", "rising", "v.", "原文為現在分詞 rising"),
    ("go", "went", "v.", "原文為過去式 went"),
    ("take", "taken", "v.", "過去分詞 taken"),
    ("shun", "shunned", "v.", "常見於外交議題。"),
    ("collide", "collided", "v.", "常見於外交議題。"),
])
def test_guide_accepts_lemma_with_article_inflection(analysis_config: Config, lemma: str,
                                                   form: str, pos: str, note: str) -> None:
    data = guide()
    example = f"The article uses {form} here."
    source = article("a1")
    source.paragraphs.append(example)
    data["vocabulary"][0].update(word=lemma, pos=pos, example_en=example, note_zh=note)
    validate_guide(data, source, analysis_config.english)


@pytest.mark.parametrize("lemma,form,note", [("go", "went", "常見搭配。"),
                                            ("shun", "unshunned", "常見搭配。"),
                                            ("collide", "planning", "搭配 planning。")])
def test_guide_rejects_unrelated_or_undocumented_forms(analysis_config: Config, lemma: str,
                                                     form: str, note: str) -> None:
    data = guide()
    example = f"The article uses {form} here."
    source = article("a1")
    source.paragraphs.append(example)
    data["vocabulary"][0].update(word=lemma, pos="v.", example_en=example, note_zh=note)
    with pytest.raises(ValueError, match="must contain"):
        validate_guide(data, source, analysis_config.english)


def test_lemma_does_not_relax_verbatim_example_check(analysis_config: Config) -> None:
    data = guide()
    source = article("a1")
    source.paragraphs.append("The firms shunned the proposal.")
    data["vocabulary"][0].update(word="shun", pos="v.", example_en="The firms shun the proposal.",
                                  note_zh="原文為過去式 shunned")
    with pytest.raises(ValueError, match="verbatim"):
        validate_guide(data, source, analysis_config.english)
