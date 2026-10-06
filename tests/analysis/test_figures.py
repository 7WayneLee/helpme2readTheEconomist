from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from econ_digest.analysis import figures
from econ_digest.analysis.cache import UnitRunner
from econ_digest.analysis.figures import (FIGURE_WARNING, describe_figures, figure_note,
                                         figure_units, validate_figures)
from econ_digest.analysis.pipeline import analyze_issue
from econ_digest.analysis.prompts import Unit
from econ_digest.cli import main
from econ_digest.config import Config, ModelsConfig
from econ_digest.images import ArticleImages, ImageBlob, IssueImages, PositionedImage, figure_image_path
from econ_digest.llm import FakeLLMClient, LLMError
from econ_digest.models import ArticleSummary, Classification
from conftest import article, issue, payload

CHART = "長條圖比較兩個地區在 2025 年的比率，單位為百分比。甲地區約 60%，高於乙地區的約 40%。"
PHOTO = "兩位行人走過城市街道，背景可見商店。"


def blobs(count: int = 1) -> list[ImageBlob]:
    return [ImageBlob(f"EPUB/images/synthetic-{index}.png", "image/png", b"synthetic pixels" + bytes([index]))
            for index in range(count)]


def article_images(count: int = 1) -> ArticleImages:
    return ArticleImages(ImageBlob("head.png", "image/png", b"head pixels"),
                         [PositionedImage(blob, index) for index, blob in enumerate(blobs(count))])


def inputs(count: int = 1):
    source = issue([article("a1")])
    classes = {"a1": Classification("a1", 0, False, None, "culture", "合成圖表文章", tier="A")}
    summaries = {"a1": ArticleSummary("a1", "A", "合成重點", structure=["第 1 段：合成脈絡"])}
    images = IssueImages(by_article={"a1": article_images(count)})
    return source, classes, summaries, images


def figure_response(prompt: str):
    return {"figures": [{"image": image["image"], "kind": "chart", "description_zh": CHART}
                        for image in payload(prompt, "圖片：")]}


@pytest.mark.parametrize("tier,level,focus,structure,allowed", [
    ("A", 1, False, True, True), ("A", 0, True, True, True), ("A", 2, True, True, True),
    ("A", 0, False, True, False), ("A", 2, False, True, False), ("A", 3, False, True, False),
    ("B", 1, True, True, False), ("C", 3, False, True, False), ("A", 1, False, False, False),
])
def test_exact_render_scope(analysis_config: Config, tier, level, focus, structure, allowed):
    source, classes, summaries, images = inputs()
    classes["a1"].taiwan_level = level
    summaries["a1"].tier = tier
    if not structure:
        summaries["a1"].structure = []
    units = figure_units(source, classes, summaries, ["a1"] if focus else [], analysis_config, images=images)
    assert bool(units) == allowed
    if allowed:
        assert units[0].article_ids == ("a1",)
        assert "head.png" not in units[0].prompt


def test_one_article_per_unit_split_at_four_and_private_extraction(analysis_config: Config):
    source, classes, summaries, images = inputs(9)
    source.articles.append(article("a2"))
    classes["a2"] = replace(classes["a1"], article_id="a2", taiwan_level=1)
    summaries["a2"] = replace(summaries["a1"], article_id="a2")
    images.by_article["a2"] = article_images(1)
    units = figure_units(source, classes, summaries, ["a1"], analysis_config, images=images)
    assert [unit.article_ids for unit in units] == [("a1",), ("a1",), ("a1",), ("a2",)]
    assert [len(payload(unit.prompt, "圖片：")) for unit in units] == [4, 4, 1, 1]
    assert units[0].models == analysis_config.llm.models.figures
    assert "只使用讀檔或讀圖工具開啟指定的圖片" in units[0].prompt
    assert "不要使用任何工具，直接回答。" not in units[0].prompt
    for unit in units:
        for image in payload(unit.prompt, "圖片："):
            path = Path(image["path"])
            assert path.is_absolute() and path.read_bytes().startswith(b"synthetic pixels")
            assert path.parent in unit.extra_read_dirs
            assert path.is_relative_to(analysis_config.paths.data_dir / "issues" / "te_2026.10.03" / "figures")


def test_image_hash_changes_only_affected_batch_cache_key(analysis_config: Config):
    source, classes, summaries, images = inputs(5)
    original = figure_units(source, classes, summaries, ["a1"], analysis_config, images=images, extract=False)
    changed = images.by_article["a1"].inline[0]
    images.by_article["a1"].inline[0] = replace(changed, image=replace(changed.image, data=b"new synthetic pixels"))
    updated = figure_units(source, classes, summaries, ["a1"], analysis_config, images=images, extract=False)
    assert original[0].prompt == updated[0].prompt
    assert original[0].cache_key != updated[0].cache_key
    assert original[1].cache_key == updated[1].cache_key
    assert not (analysis_config.paths.data_dir / "issues").exists()


def test_text_unit_cache_identity_is_unchanged():
    unit = Unit("synthetic", ("b", "a"), "test prompt", ("test model",), lambda _: None,
                "A", "prompt digest")
    old_identity = [unit.stage, sorted(unit.article_ids), unit.tier, unit.prompt_hash, list(unit.models), unit.prompt]
    assert unit.cache_key == hashlib.sha256(json.dumps(old_identity, ensure_ascii=False).encode()).hexdigest()


@pytest.mark.parametrize("names", [[], ["a.png", "a.png"], ["a.png", "extra.png"], ["b.png"]])
def test_every_requested_image_exactly_once(names):
    with pytest.raises(ValueError, match="exactly once"):
        validate_figures({"figures": [{"image": name} for name in names]}, ["a.png", "b.png"])


@pytest.mark.parametrize("data", [{}, {"figures": None}, {"figures": [None]}, {"figures": [{"image": 1}]}])
def test_invalid_envelope(data):
    with pytest.raises(ValueError, match="list of objects"):
        validate_figures(data, ["a.png"])


@pytest.mark.parametrize("kind,min_length,max_length", [("chart", 20, 160), ("map", 20, 160),
                                                        ("photo", 8, 60), ("illustration", 8, 60)])
def test_caption_length_boundaries(kind, min_length, max_length):
    for length in (min_length, max_length):
        assert len(figure_note({"kind": kind, "description_zh": "甲" * length})["description_zh"]) == length
    for length in (min_length - 1, max_length + 1):
        with pytest.raises(ValueError, match="characters"):
            figure_note({"kind": kind, "description_zh": "甲" * length})


@pytest.mark.parametrize("kind", [None, [], "diagram", "CHART", 1])
def test_invalid_kind(kind):
    with pytest.raises(ValueError, match="kind"):
        figure_note({"kind": kind, "description_zh": CHART})


@pytest.mark.parametrize("description", [None, 42, "社論" + PHOTO])
def test_invalid_description(description):
    with pytest.raises(ValueError, match="description_zh"):
        figure_note({"kind": "photo", "description_zh": description})


def test_caption_normalisation():
    result = figure_note({"kind": "illustration", "description_zh": "  晶片上的軟件顯示人工智能運算。  "})
    assert result == {"kind": "illustration", "description_zh": "晶片上的軟體顯示人工智慧運算。"}


@pytest.mark.parametrize("name", ["../escape.png", "/absolute.png", "EPUB/../../escape.png"])
def test_extraction_rejects_unsafe_names(tmp_path: Path, name):
    with pytest.raises(ValueError, match="inside"):
        figure_image_path(tmp_path / "figures", ImageBlob(name, "image/png", b"synthetic"), extract=True)


def install_images(monkeypatch, config, images):
    directory = config.paths.data_dir / "issues" / "te_2026.10.03"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "TheEconomist.2026.10.03.epub").write_bytes(b"synthetic stub; loader is mocked")
    monkeypatch.setattr(figures, "load_issue_images", lambda _: images)


def test_invalid_item_keeps_other_caption_and_warns(analysis_config, tmp_path, monkeypatch):
    source, classes, summaries, images = inputs(2)
    install_images(monkeypatch, analysis_config, images)

    def respond(prompt, *_):
        result = figure_response(prompt)
        result["figures"][0]["kind"] = "unknown"
        return result

    fake = FakeLLMClient(respond)
    warnings = []
    notes = describe_figures(source, classes, summaries, ["a1"], analysis_config,
                             UnitRunner(fake, tmp_path / "cache"), warnings)
    assert notes == {blobs(2)[1].name: {"kind": "chart", "description_zh": CHART}}
    assert warnings == [FIGURE_WARNING] and len(fake.calls) == 1
    warm = FakeLLMClient(lambda *_: pytest.fail("warm cache must avoid calls"))
    repeated_warnings = []
    assert describe_figures(source, classes, summaries, ["a1"], analysis_config,
                            UnitRunner(warm, tmp_path / "cache"), repeated_warnings) == notes
    assert warm.calls == [] and repeated_warnings == warnings


@pytest.mark.parametrize("failure", [LLMError("synthetic quota", kind="quota"), {"figures": []}])
def test_failed_unit_falls_back_without_caption(analysis_config, tmp_path, monkeypatch, failure):
    source, classes, summaries, images = inputs()
    install_images(monkeypatch, analysis_config, images)
    warnings = []
    fake = FakeLLMClient(lambda *_: failure)
    assert describe_figures(source, classes, summaries, ["a1"], analysis_config,
                            UnitRunner(fake, tmp_path / "cache"), warnings) == {}
    assert warnings == [FIGURE_WARNING]
    assert len(fake.calls) == (2 if isinstance(failure, dict) else 1)


def test_pipeline_warm_cache_zero_calls_and_read_directories(analysis_config, tmp_path, monkeypatch, fake_answer):
    source, _, _, images = inputs(5)
    install_images(monkeypatch, analysis_config, images)

    def respond(prompt, model, stage):
        return figure_response(prompt) if stage == "figures" else fake_answer(prompt, model, stage)

    fake = FakeLLMClient(respond)
    seen_directories = []

    class RecordingClient:
        def generate_json(self, prompt, **kwargs):
            if kwargs["stage"] == "figures":
                seen_directories.append(kwargs["extra_read_dirs"])
            return fake.generate_json(prompt, **kwargs)

    cache = tmp_path / "cache"
    digest = analyze_issue(source, analysis_config, RecordingClient(), workdir=cache)
    assert len(digest.figure_notes) == 5
    assert len(seen_directories) == 2 and all(seen_directories)
    assert [call[2] for call in fake.calls][-2:] == ["figures", "figures"]
    assert FIGURE_WARNING not in digest.warnings
    warm = FakeLLMClient(lambda *_: pytest.fail("warm cache must avoid calls"))
    repeated = analyze_issue(source, analysis_config, warm, workdir=cache)
    assert repeated.figure_notes == digest.figure_notes and repeated.llm_calls == [] and warm.calls == []


def test_figure_failure_cannot_abort_digest(analysis_config, tmp_path, monkeypatch, fake_answer):
    source, _, _, images = inputs(21)
    install_images(monkeypatch, analysis_config, images)

    def respond(prompt, model, stage):
        return LLMError("synthetic quota", kind="quota") if stage == "figures" else fake_answer(prompt, model, stage)

    digest = analyze_issue(source, analysis_config, FakeLLMClient(respond), workdir=tmp_path / "cache")
    assert digest.figure_notes == {} and FIGURE_WARNING in digest.warnings
    assert len([call for call in digest.llm_calls if call.stage == "figures" and not call.ok]) == 6
    assert (analysis_config.paths.data_dir / "issues" / "te_2026.10.03" / "digest.json").exists()


def test_plan_lists_figures_without_extraction_or_llm(analysis_config, monkeypatch, capsys):
    import econ_digest.commands.analyze as command
    import econ_digest.cli as cli
    source, _, _, images = inputs(5)
    install_images(monkeypatch, analysis_config, images)
    monkeypatch.setattr(cli, "load_config", lambda _: analysis_config)
    monkeypatch.setattr(command, "load_or_parse_issue", lambda *_: source)
    monkeypatch.setattr(command, "make_llm_client", lambda _: pytest.fail("plan must not call models"))
    assert main(["analyze", "--issue", source.issue_date, "--plan"]) == 0
    output = capsys.readouterr().out
    assert output.count("figures: articles=1") == 2
    assert not (analysis_config.paths.data_dir / "issues" / "te_2026.10.03" / "figures").exists()


def test_default_figure_models():
    assert ModelsConfig().figures == ("gemini-3.8-flash-high", "claude-sonnet-4-6")
