from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from econ_digest.analysis.classification import apply_tiers, fallback_classification
from econ_digest.analysis.focus import fallback_focus, focus_candidates, focus_unit, validate_focus
from econ_digest.analysis.pipeline import analyze_issue
from econ_digest.analysis.planning import plan_issue
from econ_digest.analysis.prompts import PROMPT_DIR
from econ_digest.analysis.validation import validate_summary
from econ_digest.config import AnalysisConfig, Config
from econ_digest.llm import FakeLLMClient
from econ_digest.models import Digest, load_json
from econ_digest.render.common import sections
from econ_digest.render.telegraph import render_telegraph
from econ_digest.site import build_site

from conftest import answer, article, issue, payload, summary


def test_every_focus_article_remains_level_zero_and_on_focus_pages(analysis_config, tmp_path):
    source = issue([article(f'a{i}') for i in range(1, 4)])

    def responder(prompt, model, stage):
        data = answer(prompt, model, stage)
        if stage == 'ground':
            for proposed, item in enumerate(data['articles'], 1):
                item.update(taiwan_level=proposed,
                            taiwan_link={'text_zh': '合成政策改變台灣企業成本。', 'basis': ['article', 'facts']},
                            taiwan_implications=[{'text_zh': '（推論）合成政策增加台灣企業成本。',
                                                  'basis': ['article', 'facts']}])
        return data

    digest = analyze_issue(source, analysis_config, FakeLLMClient(responder), workdir=tmp_path / 'analysis')
    assert len(digest.focus_ids) == 3
    assert all(digest.classifications[identifier].taiwan_level == 0
               and digest.classifications[identifier].taiwan_link is None
               and digest.classifications[identifier].sources == []
               and digest.classifications[identifier].tier == digest.summaries[identifier].tier == 'A'
               for identifier in digest.focus_ids)
    assert [entry.article.id for section in sections(digest) if section.anchor == 'focus'
            for entry in section.entries] == digest.focus_ids
    site = build_site(digest, tmp_path / 'site')
    focus_html = site.pages['focus'].read_text()
    telegraph_focus = json.dumps([page.nodes for page in render_telegraph(digest) if page.key.startswith('focus:')])
    for story in source.articles:
        assert story.title in focus_html and story.title in telegraph_focus
        assert digest.summaries[story.id].taiwan_implications == ['（推論）合成政策增加台灣企業成本。']


def classified(source, config):
    classifications = {item.id: fallback_classification(item) for item in source.articles}
    apply_tiers(source.articles, classifications, config.tiers)
    return classifications


def test_candidates_exclude_taiwan_and_special_kinds(analysis_config: Config) -> None:
    excluded = ["letters", "obituary", "cartoon", "indicators", "world_politics", "world_business"]
    source = issue([article("allowed"), article("cover", kind="briefing"), article("leader", kind="leader"),
                    article("merged", kind="leader"), *(article(f"t{level}") for level in (1, 2, 3)),
                    *(article(kind, kind=kind) for kind in excluded),
                    *(article(tier) for tier in ("merged", "brief", "skip"))])
    classifications = classified(source, analysis_config)
    classifications["merged"].tier = "merged"
    for level in (1, 2, 3):
        classifications[f"t{level}"].taiwan_level = level
    for tier in ("merged", "brief", "skip"):
        classifications[tier].tier = tier
    assert [item.id for item in focus_candidates(source, classifications)] == ["allowed", "cover", "leader"]


def test_focus_metadata_and_configured_count(analysis_config: Config) -> None:
    source = issue([article("l1", kind="leader", cover=True), article("a1"), article("a2")])
    classifications = classified(source, analysis_config)
    classifications["l1"].companion_id = "a1"
    apply_tiers(source.articles, classifications, analysis_config.tiers)
    config = replace(analysis_config, analysis=AnalysisConfig(focus_count=5))
    unit = focus_unit(source, classifications, config)
    candidates = payload(unit.prompt, "候選：")
    assert unit.models == config.llm.models.focus and unit.stage == "focus"
    assert "的 2 篇" in unit.prompt
    assert candidates[0] == {"id": "a1", "section": "Culture", "kind": "article", "fly_title": None,
                             "title": "Synthetic a1", "rubric": "Synthetic rubric", "title_zh": "Synthetic a1",
                             "category": "culture", "tier": "B", "word_count": 100,
                             "is_cover_companion": True, "has_merged_leader": True}
    assert not candidates[1]["is_cover_companion"] and not candidates[1]["has_merged_leader"]
    assert unit.cache_key == focus_unit(source, classifications, analysis_config).cache_key
    smaller = replace(config, analysis=AnalysisConfig(focus_count=1))
    assert unit.cache_key != focus_unit(source, classifications, smaller).cache_key
    changed_models = replace(config, llm=replace(config.llm, models=replace(config.llm.models, focus=("other",))))
    assert unit.cache_key != focus_unit(source, classifications, changed_models).cache_key
    unit.validate({"focus": [{"article_id": "a2", "reason": "全球經濟重要議題。"},
                             {"article_id": "a1", "reason": "本週封面重點。"}]})


@pytest.mark.parametrize("data", [
    {}, {"focus": []}, {"focus": [{"article_id": "a", "reason": "重要。"}]},
    {"focus": [{"article_id": "a", "reason": "重要。"}] * 2},
    {"focus": [{"article_id": "a", "reason": "重要。"}, {"article_id": "outside", "reason": "重要。"}]},
    {"focus": [{"article_id": "a", "reason": ""}, {"article_id": "b", "reason": "重要。"}]},
    {"focus": [{"article_id": "a", "reason": "English only."}, {"article_id": "b", "reason": "重要。"}]},
    {"focus": [{"article_id": "a", "reason": "第一句。第二句。"}, {"article_id": "b", "reason": "重要。"}]},
    {"focus": ["a", "b"]},
    {"focus": [{"article_id": [], "reason": "重要。"}, {"article_id": "b", "reason": "重要。"}]},
])
def test_focus_validation_rejects_bad_decisions(data: dict) -> None:
    with pytest.raises(ValueError):
        validate_focus(data, {"a", "b", "c"}, 2)


def test_focus_validation_accepts_order_and_smaller_pool() -> None:
    data = {"focus": [{"article_id": "b", "reason": "本週的重要議題。"},
                      {"article_id": "a", "reason": "長期後果值得關注。"}]}
    validate_focus(data, {"a", "b"}, 3)
    assert [item["article_id"] for item in data["focus"]] == ["b", "a"]


def test_fallback_priorities_and_tie_breaks(analysis_config: Config) -> None:
    source = issue([article("c1", words=2000), article("c2", words=4000), article("b1", kind="briefing", words=500),
                    article("a1", words=300), article("a2", words=1000), article("e1", words=9000),
                    article("l1", kind="leader", cover=True), article("l2", kind="leader")])
    classifications = classified(source, analysis_config)
    classifications["l1"].companion_id = "a1"
    classifications["l2"].companion_id = "a2"
    apply_tiers(source.articles, classifications, analysis_config.tiers)
    for identifier in ("c1", "c2"):
        classifications[identifier].tier = "C"
    data = fallback_focus(source, classifications, 6)
    assert [item["article_id"] for item in data["focus"]] == ["a1", "b1", "a2", "c2", "c1", "e1"]
    source.articles.reverse()
    assert fallback_focus(source, classifications, 6) == data
    validate_focus(data, {item.id for item in focus_candidates(source, classifications)}, 6)


def test_order_tier_override_persistence_and_warm_cache(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article("特朗普" if i == 4 else f"a{i}") for i in range(6)])

    def responder(prompt, model, stage):
        if stage == "focus":
            return {"focus": [{"article_id": identifier, "reason": "全球重要性與長期後果值得分析。"}
                              for identifier in ["特朗普", "a1", "a3"]]}
        return answer(prompt, model, stage)

    cache = tmp_path / "analysis"
    client = FakeLLMClient(responder)
    digest = analyze_issue(source, analysis_config, client, workdir=cache)
    assert digest.focus_ids == ["特朗普", "a1", "a3"]
    assert all(digest.classifications[identifier].tier == digest.summaries[identifier].tier == "A"
               for identifier in digest.focus_ids)
    assert digest.classifications["a0"].tier == "E"
    assert sum(stage == "focus" for _, _, stage in client.calls) == 1
    saved = analysis_config.paths.data_dir / "issues" / "te_2026.10.03" / "digest.json"
    assert load_json(saved, Digest).focus_ids == digest.focus_ids
    warm = FakeLLMClient(lambda *args: pytest.fail("warm cache must prevent all calls"))
    rerun = analyze_issue(source, analysis_config, warm, workdir=cache)
    assert warm.calls == [] and rerun.llm_calls == [] and rerun.focus_ids == digest.focus_ids
    units, estimated = plan_issue(source, analysis_config, workdir=cache)
    assert not estimated and any(unit.stage == "focus" for unit in units)


def test_exhausted_models_fallback_warning_and_warm_cache(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article("a1")])
    config = replace(analysis_config, llm=replace(analysis_config.llm,
                     models=replace(analysis_config.llm.models, focus=("first", "second"))))

    def responder(prompt, model, stage):
        return {"focus": []} if stage == "focus" else answer(prompt, model, stage)

    cache = tmp_path / "analysis"
    client = FakeLLMClient(responder)
    digest = analyze_issue(source, config, client, workdir=cache)
    assert digest.focus_ids == ["a1"] and digest.summaries["a1"].tier == "A"
    assert [model for _, model, stage in client.calls if stage == "focus"] == ["first", "first", "second", "second"]
    assert any("焦點選文失敗" in warning and "固定排序" in warning for warning in digest.warnings)
    warm = FakeLLMClient(lambda *args: pytest.fail("fallback decision must also be cached"))
    rerun = analyze_issue(source, config, warm, workdir=cache)
    assert warm.calls == [] and rerun.focus_ids == digest.focus_ids and rerun.warnings == digest.warnings


def test_no_candidates_does_not_call_focus(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article("a1", kind="letters")])
    client = FakeLLMClient(answer)
    digest = analyze_issue(source, analysis_config, client, workdir=tmp_path / "analysis")
    assert digest.focus_ids == [] and not any(stage == "focus" for _, _, stage in client.calls)


def test_focus_preserves_merged_leader_in_a_summary(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article("l1", kind="leader", cover=True), article("a1"), article("a2")])

    def responder(prompt, model, stage):
        data = answer(prompt, model, stage)
        if stage == "pair":
            data["pairs"][0]["companion_id"] = "a1"
        return data

    client = FakeLLMClient(responder)
    digest = analyze_issue(source, analysis_config, client, workdir=tmp_path / "analysis")
    assert digest.focus_ids == ["a1", "a2"] and digest.classifications["l1"].tier == "merged"
    assert digest.summaries["a1"].leader_stance.startswith("作者主張：")
    assert digest.summaries["a1"].tier == "A"
    inputs = [item for prompt, _, stage in client.calls if stage == "summarize_a"
              for item in payload(prompt, "文章：") if item["article_id"] == "a1"]
    assert len(inputs) == 1 and inputs[0]["leader"]["article_id"] == "l1"


def test_changed_focus_reuses_unaffected_summary_units(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article(f"a{i}") for i in range(40)])
    cache = tmp_path / "analysis"
    original = analyze_issue(source, analysis_config, FakeLLMClient(answer), workdir=cache)
    path = next(cache.glob("focus-*.json"))
    envelope = json.loads(path.read_text())
    envelope["data"]["focus"] = [{"article_id": identifier, "reason": "不同的重要趨勢值得分析。"}
                                for identifier in ["a0", "a1", "a13"]]
    path.write_text(json.dumps(envelope))
    client = FakeLLMClient(answer)
    digest = analyze_issue(source, analysis_config, client, workdir=cache)
    assert original.focus_ids == ["a0", "a1", "a2"] and digest.focus_ids == ["a0", "a1", "a13"]
    summary_calls = [(stage, {item["article_id"] for item in payload(prompt, "文章：")})
                     for prompt, _, stage in client.calls if stage.startswith("summarize_")]
    assert len(summary_calls) == 3
    assert ("summarize_a", {"a13"}) in summary_calls
    assert all(stage.startswith("summarize_") for stage, _ in summary_calls)
    assert not any(ids & {f"a{i}" for i in range(24, 40)} for _, ids in summary_calls)


def test_prompts_and_validation_use_author_stance() -> None:
    for path in PROMPT_DIR.glob("*.md"):
        content = path.read_text()
        if path.name == "_style.md":
            assert "絕對禁用「社論」二字" in content
            continue
        if path.name == "_common.md":
            assert "不得寫「社論」" in content
            assert "經濟學人立場（Leaders）" in content
            content = content.replace("不得寫「社論」", "")
        assert "社論" not in content, path.name
        if path.name.startswith("summarize_"):
            assert "作者主張：" in path.read_text() and "經濟學人立場" in path.read_text()
    data = summary("a1", "C", leader=True)
    validate_summary(data, article("a1"), "C", leader=True)
    data["leader_stance"] = data["leader_stance"].replace("作者主張：", "社論主張：")
    with pytest.raises(ValueError, match="作者主張：") as caught:
        validate_summary(data, article("a1"), "C", leader=True)
    assert "社論" not in str(caught.value)
