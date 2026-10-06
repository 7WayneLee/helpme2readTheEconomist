from __future__ import annotations

from pathlib import Path

import pytest

from econ_digest.analysis.classification import classify_units, fallback_classification
from econ_digest.analysis.english import english_candidates, pick_unit
from econ_digest.analysis.summaries import BATCH_LIMITS, summary_units
from econ_digest.analysis.prompts import PROMPT_DIR
from econ_digest.cli import main
from econ_digest.config import Config
from econ_digest.models import Issue
from conftest import article, issue


def test_english_filter_and_history(analysis_config: Config) -> None:
    source = issue([article("a1", words=600), article("a2", words=1300), article("a3", words=599),
                    article("a4", words=1301), article("a5", kind="letters", words=800),
                    article("l1", kind="leader", words=800), article("o1", kind="obituary", words=800)])
    assert [item.id for item in english_candidates(source, analysis_config)] == ["a1", "a2", "l1", "o1"]
    classifications = {item.id: fallback_classification(item) for item in source.articles}
    history = [{"section": f"Section {i}", "kind": "column", "title": f"History {i}"} for i in range(12)]
    unit = pick_unit(source, classifications, analysis_config, history)
    assert "History 3" not in unit.prompt and "History 4" in unit.prompt and "History 11" in unit.prompt
    assert "避免最近兩次" in unit.prompt and "B1–B2" in unit.prompt and "B2–C1" in unit.prompt


def test_repick_excludes_failed_article_and_changes_cache_key(analysis_config: Config) -> None:
    source = issue([article("a1", words=800), article("a2", words=800)])
    classifications = {item.id: fallback_classification(item) for item in source.articles}
    original = pick_unit(source, classifications, analysis_config)
    retry = pick_unit(source, classifications, analysis_config, exclude_ids=frozenset({"a1"}))
    assert retry.article_ids == ("a2",) and '"id":"a1"' not in retry.prompt
    assert retry.cache_key != original.cache_key
    with pytest.raises(ValueError, match="eligible"):
        retry.validate({"article_id": "a1", "reason_zh": "理由。"})
    assert pick_unit(source, classifications, analysis_config, exclude_ids=frozenset({"a1", "a2"})) is None


@pytest.mark.parametrize("tier", list("ABCDE"))
def test_large_issue_prompt_limits(tier: str, analysis_config: Config) -> None:
    paragraphs = [" ".join(["synthetic"] * 140)] * 20
    source = issue([article(f"a{i}", paragraphs=paragraphs, words=2800) for i in range(80)])
    classifications = {item.id: fallback_classification(item) for item in source.articles}
    for classification in classifications.values():
        classification.tier = tier
    units = summary_units(source, classifications, analysis_config)
    assert sum(len(unit.article_ids) for unit in units) == 80
    assert all(len(unit.article_ids) <= BATCH_LIMITS[tier] and unit.prompt_bytes <= 90_000 for unit in units)
    assert len(classify_units(source, analysis_config)) == 4
    assert all(unit.prompt_bytes <= 60_000 for unit in classify_units(source, analysis_config))


def test_oversized_single_article_is_rejected(analysis_config: Config) -> None:
    source = issue([article("a1", paragraphs=["x" * 100_000])])
    classifications = {"a1": fallback_classification(source.articles[0])}
    classifications["a1"].tier = "A"
    with pytest.raises(ValueError, match="exceeds"):
        summary_units(source, classifications, analysis_config)


def test_plan_no_llm_and_filters(analysis_config: Config, example_issue: Issue, monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    import econ_digest.commands.analyze as command
    import econ_digest.cli as cli
    monkeypatch.setattr(cli, "load_config", lambda _: analysis_config)
    monkeypatch.setattr(command, "load_or_parse_issue", lambda *args: example_issue)
    monkeypatch.setattr(command, "make_llm_client", lambda _: pytest.fail("plan must not construct a client"))
    assert main(["analyze", "--issue", "2026.10.03", "--plan", "--only-tier", "E", "--limit", "2"]) == 0
    output = capsys.readouterr().out
    assert "classify:" in output and "focus:" in output and "summarize_e: articles=2" in output and "brief:" in output
    assert "prompt_bytes=" in output and "models=fake" in output and "最大提示詞" in output
    assert not (analysis_config.paths.data_dir / "issues" / "te_2026.10.03" / "digest.json").exists()


def test_all_prompt_files_exist() -> None:
    expected = {"_common.md", "_style.md", "edit.md", "ground_queries.md", "ground.md", "facts.md", "figures.md",
                "classify.md", "pair.md", "focus.md", "brief.md", "english_pick.md", "english_guide.md",
                *(f"summarize_{tier}.md" for tier in "abcde")}
    assert {path.name for path in PROMPT_DIR.glob("*.md")} == expected
