from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from econ_digest import models
from econ_digest.models import (
    Argument, Article, ArticleSummary, BriefItem, Classification, Digest, EnglishPick,
    Issue, LLMCallStat, PhraseItem, QuizItem, Quote, SentenceAnalysis, TaiwanSignals,
    VocabItem, WeekBrief, load_json, save_json,
)
from econ_digest.state import AlreadyRunning, StateError, StateStore, load_state, run_lock, save_state


def all_models() -> list[models.JsonModel]:
    article = Article("a", 0, "Synthetic", None, "Synthetic title", None, None, ["Invented text."], 2, "article")
    issue = Issue("2026.10.03", "https://example.invalid", "2026-10-03T00:00:00+00:00", [article])
    signals = TaiwanSignals(["Taiwan"], ["chips"], 1, ["Taiwan makes invented chips."])
    classification = Classification("a", 1, True, "台灣是主題。", "tech", "合成標題", "b", "A")
    quote = Quote("Synthetic quote.", "合成引言。")
    argument = Argument("主張", ["證據"], ["反論"], "結論")
    summary = ArticleSummary("a", "A", "合成標題", "摘要", ["重點"], "背景", ["脈絡"], argument,
                             ["數據"], [quote], "立場", ["台灣影響"], ["問題"], "社論觀點", "synthetic-model")
    brief_item = BriefItem("本週合成要聞。", True)
    brief = WeekBrief([brief_item], [BriefItem("商業合成要聞。")])
    vocabulary = VocabItem("invented", "adj.", "虛構的", "An invented story.", "合成註解")
    phrase = PhraseItem("make up", "編造", "Make up a story.")
    sentence = SentenceAnalysis("An invented sentence.", "合成分析", "虛構句子。")
    quiz = QuizItem("What is invented?", "The story.")
    english = EnglishPick("a", "合成原因", "B1", 800, 4, "閱讀前", [vocabulary], [phrase], [sentence], ["寫作技巧"], [quiz])
    stat = LLMCallStat("classify", "synthetic-model", True, 42, 1.25)
    digest = Digest("2026.10.03", "2026-10-04T00:00:00Z", issue, {"a": classification}, {"a": summary}, brief, english, [stat], ["合成警告"])
    return [article, issue, signals, classification, quote, argument, summary, brief_item, brief,
            vocabulary, phrase, sentence, quiz, english, stat, digest]


@pytest.mark.parametrize("instance", all_models(), ids=lambda obj: type(obj).__name__)
def test_every_dataclass_json_round_trip(instance: models.JsonModel, tmp_path: Path) -> None:
    decoded = type(instance).from_dict(json.loads(json.dumps(instance.to_dict(), ensure_ascii=False)))
    assert decoded == instance
    path = tmp_path / "nested" / "model.json"
    save_json(path, instance)
    assert load_json(path, type(instance)) == instance
    assert path.read_text(encoding="utf-8").startswith("{\n  ")


def test_all_model_dataclasses_are_covered() -> None:
    declared = {value for value in vars(models).values() if isinstance(value, type) and is_dataclass(value)}
    assert declared == {type(value) for value in all_models()}


def test_nested_types_and_optional_defaults_are_restored() -> None:
    digest = all_models()[-1]
    restored = Digest.from_dict(digest.to_dict())
    assert isinstance(restored.issue.articles[0], Article)
    assert isinstance(restored.classifications["a"], Classification)
    assert isinstance(restored.summaries["a"].argument, Argument)
    assert isinstance(restored.summaries["a"].quotes[0], Quote)
    assert restored.english is not None and isinstance(restored.english.vocabulary[0], VocabItem)
    data = digest.to_dict()
    data["week_brief"] = data["english"] = None
    assert Digest.from_dict(data).english is None
    assert ArticleSummary.from_dict({"article_id": "a", "tier": "E", "headline_zh": "一句話"}).key_points == []


def test_atomic_json_unicode_and_failure_preserves_old_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "state.json"
    save_json(path, {"正體中文": "台灣"})
    assert "台灣" in path.read_text(encoding="utf-8")
    original = path.read_bytes()

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(models.os, "replace", fail_replace)
    with pytest.raises(OSError):
        save_json(path, {"new": "value"})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_state_history_and_delivery_round_trip(tmp_path: Path, synthetic_article: Article) -> None:
    state = load_state(tmp_path)
    assert state["delivered"] == {} and state["english_history"] == []
    store = StateStore(tmp_path)
    store.start_run("2026.10.03")
    store.mark_delivered("2026.10.03", 4)
    store.record_english("2026.10.03", synthetic_article)
    store.record_english("2026.10.03", synthetic_article)
    store.finish_run("succeeded")
    state = store.load()
    assert store.is_delivered("2026.10.03")
    assert not store.is_delivered("2026.09.26")
    assert state["delivered"]["2026.10.03"]["message_count"] == 4
    assert len(state["english_history"]) == 1
    assert set(state["english_history"][0]) == {"issue_date", "article_id", "section", "kind", "title"}
    assert state["last_run"]["outcome"] == "succeeded"
    assert state["last_run"]["finished_at"] is not None
    save_state(tmp_path, state)
    assert load_state(tmp_path) == state


def test_corrupt_state_is_not_reset(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text("broken", encoding="utf-8")
    with pytest.raises(StateError):
        load_state(tmp_path)


def test_lock_contention_release_and_exception_cleanup(tmp_path: Path) -> None:
    with run_lock(tmp_path):
        with pytest.raises(AlreadyRunning):
            with run_lock(tmp_path):
                pytest.fail("contending lock was acquired")
    with pytest.raises(ValueError):
        with run_lock(tmp_path):
            raise ValueError("synthetic failure")
    with run_lock(tmp_path):
        assert (tmp_path / ".lock").exists()
