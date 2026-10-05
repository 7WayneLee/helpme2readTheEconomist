from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from econ_digest.analysis.pipeline import AnalysisError, analyze_issue, analyze_selected, make_llm_client
from econ_digest.config import Config
from econ_digest.llm import FakeLLMClient, GwgClient, LLMError
from econ_digest.models import Digest, Issue, load_json

from conftest import answer, article, issue


def test_digest_normalisation_cache_and_persistence(analysis_config: Config, tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    source = issue([article("a1", words=800), article("a2"),
                    article("p1", kind="world_politics", paragraphs=["Synthetic news."]),
                    article("b1", kind="world_business", paragraphs=["Synthetic business."]),
                    article("c1", kind="cartoon")])

    def responder(prompt: str, model: str, stage: str) -> dict:
        data = answer(prompt, model, stage)
        if stage == "classify":
            for item in data["articles"]:
                item["title_zh"] = "特朗普宣布软件产业的新计划"
        if stage == "brief":
            data["politics"][0]["text_zh"] = "政府宣佈新政策，公佈地區分佈。"
        return data

    fake = FakeLLMClient(responder)
    cache = tmp_path / "analysis"
    digest = analyze_issue(source, analysis_config, fake, workdir=cache)
    assert digest.classifications["a1"].title_zh == "川普宣布軟體產業的新計畫"
    assert digest.week_brief.politics[0].text_zh == "政府宣布新政策，公布地區分布。"
    assert digest.classifications["c1"].tier == "skip"
    assert digest.english.word_count == 800 and digest.english.reading_minutes == 6
    assert digest.english.vocabulary[0].example_en == "A policy needs resolve and careful planning."
    assert len(digest.llm_calls) == 5 and all(stat.ok for stat in digest.llm_calls)
    saved = analysis_config.paths.data_dir / "issues" / "te_2026.10.03" / "digest.json"
    assert load_json(saved, Digest).to_dict() == digest.to_dict()
    import json
    from econ_digest.analysis import pipeline
    from econ_digest.analysis.cache import CACHE_FORMAT_VERSION
    envelope = json.loads(next(cache.glob("classify-*.json")).read_text())
    assert envelope["format_version"] == CACHE_FORMAT_VERSION
    assert envelope["data"]["articles"][0]["title_zh"] == "特朗普宣布软件产业的新计划"
    second = FakeLLMClient(lambda *args: AssertionError("cache must prevent calls"))
    rerun = analyze_issue(source, analysis_config, second, workdir=cache)
    assert second.calls == [] and rerun.llm_calls == []
    assert rerun.english.to_dict() == digest.english.to_dict()
    original_normalize = pipeline.normalize_tree

    def updated_normalize(value: Any, **kwargs: Any) -> Any:
        result = original_normalize(value, **kwargs)
        result["classifications"]["a1"]["title_zh"] = "更新後的中文標題"
        result["summaries"]["a1"]["headline_zh"] = "残留问题"
        return result

    monkeypatch.setattr(pipeline, "normalize_tree", updated_normalize)
    updated = analyze_issue(source, analysis_config, second, workdir=cache)
    assert second.calls == [] and updated.llm_calls == []
    assert updated.classifications["a1"].title_zh == "更新後的中文標題"
    assert updated.issue.to_dict() == source.to_dict()
    assert any("簡體字" in warning and "题" in warning for warning in updated.warnings)
    assert json.loads(next(cache.glob("classify-*.json")).read_text()) == envelope


def test_missing_ids_uses_client_repair(analysis_config: Config, example_issue: Issue, tmp_path: Path) -> None:
    seen = 0

    def responder(prompt: str, model: str, stage: str) -> dict:
        nonlocal seen
        if stage == "classify":
            seen += 1
            if seen == 1:
                return {"articles": []}
            assert "上一次的輸出無法使用" in prompt
        return answer(prompt, model, stage)

    fake = FakeLLMClient(responder)
    digest = analyze_issue(example_issue, analysis_config, fake, workdir=tmp_path / "analysis")
    assert seen == 2
    assert all(stat.ok for stat in digest.llm_calls)
    assert not any("分類失敗" in warning for warning in digest.warnings)


def test_signal_warning(analysis_config: Config, tmp_path: Path) -> None:
    digest = analyze_issue(issue([article("a1", paragraphs=["Taiwan " * 12])]), analysis_config,
                           FakeLLMClient(answer), workdir=tmp_path / "analysis")
    assert any("提及 12 次" in warning and "等級為 0" in warning for warning in digest.warnings)


def test_one_failed_classification_batch_falls_back(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article(f"a{i}", paragraphs=["Taiwan is a synthetic location."]) for i in range(25)])

    def responder(prompt: str, model: str, stage: str) -> dict[str, Any] | LLMError:
        if stage == "classify" and '"id":"a0"' in prompt:
            return LLMError("synthetic quota", kind="quota")
        return answer(prompt, model, stage)

    digest = analyze_issue(source, analysis_config, FakeLLMClient(responder), workdir=tmp_path / "analysis")
    assert digest.classifications["a0"].taiwan_level == 3
    assert digest.classifications["a0"].title_zh == "Synthetic a0"
    assert any("分類失敗" in warning for warning in digest.warnings)
    assert sum(not stat.ok for stat in digest.llm_calls) == 1


def test_one_failed_summary_unit_falls_back(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article(f"a{i}") for i in range(40)])

    def responder(prompt: str, model: str, stage: str) -> dict[str, Any] | LLMError:
        if stage == "summarize_e" and '"article_id":"a0"' in prompt:
            return LLMError("synthetic quota", kind="quota")
        return answer(prompt, model, stage)

    digest = analyze_issue(source, analysis_config, FakeLLMClient(responder), workdir=tmp_path / "analysis")
    assert digest.summaries["a0"].headline_zh == "（摘要產生失敗）Synthetic a0"
    assert digest.summaries["a39"].model == "fake"
    assert any("摘要失敗" in warning for warning in digest.warnings)


def test_failure_threshold_leaves_no_digest(analysis_config: Config, tmp_path: Path) -> None:
    fake = FakeLLMClient(lambda *args: LLMError("synthetic quota", kind="quota"))
    with pytest.raises(AnalysisError, match="超過 30%"):
        analyze_issue(issue([article("a1")]), analysis_config, fake, workdir=tmp_path / "analysis")
    assert not (analysis_config.paths.data_dir / "issues" / "te_2026.10.03" / "digest.json").exists()


def test_english_failure_gives_none_and_warning(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article(f"a{i}", words=800 if i == 0 else 100) for i in range(25)])

    def responder(prompt: str, model: str, stage: str) -> dict[str, Any] | LLMError:
        return LLMError("synthetic quota", kind="quota") if stage == "english_pick" else answer(prompt, model, stage)

    digest = analyze_issue(source, analysis_config, FakeLLMClient(responder), workdir=tmp_path / "analysis")
    assert digest.english is None and any("英文選文失敗" in warning for warning in digest.warnings)


def test_cover_pair_and_quote_repair(analysis_config: Config, tmp_path: Path) -> None:
    source = issue([article("l1", kind="leader", cover=True), article("a1"), article("a2")])
    bad_quote_sent = False

    def responder(prompt: str, model: str, stage: str) -> dict:
        nonlocal bad_quote_sent
        data = answer(prompt, model, stage)
        if stage == "classify":
            data["articles"][1]["taiwan_level"] = 1
            data["articles"][1]["taiwan_link"] = "台灣是主題。"
        elif stage == "pair":
            data["pairs"][0]["companion_id"] = "a1"
        elif stage == "summarize_a" and not bad_quote_sent:
            data["articles"][0]["quotes"][0]["en"] = "Fabricated sentence."
            bad_quote_sent = True
        return data

    fake = FakeLLMClient(responder)
    digest = analyze_issue(source, analysis_config, fake, workdir=tmp_path / "analysis")
    assert digest.classifications["l1"].tier == "merged"
    assert digest.classifications["a1"].tier == "A"
    assert digest.summaries["a1"].leader_stance.startswith("社論主張：")
    assert len([call for call in fake.calls if call[2] == "summarize_a"]) == 2


def test_cache_key_changes_with_models_text_and_history(analysis_config: Config, tmp_path: Path) -> None:
    from econ_digest.analysis.classification import classify_units
    from econ_digest.analysis.english import pick_unit
    from econ_digest.models import Classification
    source = issue([article("a1", words=800)])
    classifications = {"a1": Classification("a1", 0, False, None, "culture", "測試")}
    first = classify_units(source, analysis_config)[0]
    changed = issue([replace(source.articles[0], paragraphs=["Different source."])])
    assert first.cache_key != classify_units(changed, analysis_config)[0].cache_key
    models = replace(analysis_config.llm.models, classify=("different",))
    assert first.cache_key != classify_units(source, replace(analysis_config, llm=replace(analysis_config.llm, models=models)))[0].cache_key
    assert pick_unit(source, classifications, analysis_config, []).cache_key != pick_unit(
        source, classifications, analysis_config, [{"section": "Culture", "kind": "article", "title": "Previous"}]).cache_key


def test_corrupt_cache_is_regenerated(analysis_config: Config, example_issue: Issue, tmp_path: Path) -> None:
    cache = tmp_path / "analysis"
    analyze_issue(example_issue, analysis_config, FakeLLMClient(answer), workdir=cache)
    next(cache.glob("classify-*.json")).write_text("{broken")
    fake = FakeLLMClient(answer)
    analyze_issue(example_issue, analysis_config, fake, workdir=cache)
    assert len(fake.calls) == 1 and fake.calls[0][2] == "classify"


@pytest.mark.parametrize("version", [None, 1])
def test_old_normalised_cache_is_regenerated_once(analysis_config: Config, example_issue: Issue,
                                                 tmp_path: Path, version: int | None) -> None:
    import json
    from econ_digest.analysis.cache import CACHE_FORMAT_VERSION
    cache = tmp_path / "analysis"
    analyze_issue(example_issue, analysis_config, FakeLLMClient(answer), workdir=cache)
    path = next(cache.glob("classify-*.json"))
    envelope = json.loads(path.read_text())
    if version is None:
        del envelope["format_version"]
    else:
        envelope["format_version"] = version
    path.write_text(json.dumps(envelope))
    fake = FakeLLMClient(answer)
    analyze_issue(example_issue, analysis_config, fake, workdir=cache)
    assert len(fake.calls) == 1 and fake.calls[0][2] == "classify"
    assert json.loads(path.read_text())["format_version"] == CACHE_FORMAT_VERSION
    warm = FakeLLMClient(lambda *args: AssertionError("cache must prevent calls"))
    analyze_issue(example_issue, analysis_config, warm, workdir=cache)
    assert warm.calls == []


def test_limited_run_preserves_full_digest(analysis_config: Config, example_issue: Issue, tmp_path: Path) -> None:
    cache = tmp_path / "analysis"
    analyze_issue(example_issue, analysis_config, FakeLLMClient(answer), workdir=cache)
    saved = analysis_config.paths.data_dir / "issues" / "te_2026.10.03" / "digest.json"
    original = saved.read_bytes()
    digest = analyze_selected(example_issue, analysis_config, FakeLLMClient(answer), workdir=cache, only_tier="E", limit=1)
    assert len(digest.summaries) == 1 and saved.read_bytes() == original
    assert saved.with_name("digest-tuning.json").exists()


def test_make_llm_client(analysis_config: Config) -> None:
    client = make_llm_client(analysis_config)
    assert isinstance(client, GwgClient)
    assert client.workdir == analysis_config.paths.data_dir / "agy-workdir"
    assert client.call_timeout == analysis_config.llm.call_timeout_seconds


def test_default_gwg_is_blocked_by_test_quota_guard(tmp_path: Path) -> None:
    import os
    if os.environ.get("ECON_DIGEST_LIVE_GWG") == "1":
        pytest.skip("live gwg was explicitly enabled")
    client = GwgClient("gwg", workdir=tmp_path / "gwg-workdir", no_account_wait=0)
    with pytest.raises(LLMError, match="live gwg disabled in tests") as info:
        client.generate_json("Synthetic prompt", models=["synthetic-model"])
    assert info.value.kind == "error" and len(info.value.attempts) == 2
