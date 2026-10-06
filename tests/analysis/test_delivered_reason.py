"""Delivered reasons survive reuse and stay reader-facing in every renderer."""

import json
from pathlib import Path

import pytest

from econ_digest.analysis.pipeline import analyze_issue
from econ_digest.analysis.planning import plan_issue
from econ_digest.config import Config
from econ_digest.fetch import issue_directory
from econ_digest.llm import FakeLLMClient
from econ_digest.models import save_json
from econ_digest.render import render_html, render_markdown, render_telegram
from econ_digest.render.telegraph import render_telegraph
from econ_digest.site import build_site
from conftest import answer, article, issue

HISTORY_REASON = "論證清楚，適合練習條件句。"
DIGEST_REASON = "主題貼近日常生活，例句有助於練習轉折語氣。"
INTERNAL_NOTE = "沿用本期最近一次已送出的英文選文。"


@pytest.mark.parametrize("reason_source", ["history", "digest", "missing"])
def test_delivered_reason_recovery_and_all_renderers(analysis_config: Config, tmp_path: Path,
                                                    reason_source: str) -> None:
    source = issue([article("a1", words=800), article("a2", words=800)])
    history = [{"issue_date": source.issue_date, "article_id": "a2"}]
    directory = issue_directory(analysis_config, source.issue_date)
    if reason_source == "history":
        history[0]["reason_zh"] = HISTORY_REASON
    if reason_source != "missing":
        save_json(directory / "digest.json", {"issue_date": source.issue_date,
                  "english": {"article_id": "a2", "reason_zh": DIGEST_REASON}})
    expected_reason = {"history": HISTORY_REASON, "digest": DIGEST_REASON,
                       "missing": "結構清楚，單字實用。"}[reason_source]
    cache = tmp_path / "analysis"
    planned, _ = plan_issue(source, analysis_config, workdir=cache, english_history=history)
    assert sum(unit.stage == "english_pick" for unit in planned) == (reason_source == "missing")
    client = FakeLLMClient(answer)
    digest = analyze_issue(source, analysis_config, client, workdir=cache, english_history=history)
    assert digest.english.article_id == ("a1" if reason_source == "missing" else "a2")
    assert digest.english.reason_zh == expected_reason
    assert sum(stage == "english_pick" for _, _, stage in client.calls) == (reason_source == "missing")
    assert any("缺少選文理由" in warning and "重新選文" in warning
               for warning in digest.warnings) == (reason_source == "missing")

    site = build_site(digest, tmp_path / "site")
    outputs = [render_markdown(digest), render_html(digest), *render_telegram(digest),
               json.dumps([page.nodes for page in render_telegraph(digest)], ensure_ascii=False),
               *(path.read_text(encoding="utf-8") for path in site.pages.values())]
    assert all("沿用本期" not in output for output in outputs)
    assert expected_reason in render_markdown(digest)
    assert expected_reason in render_html(digest)
    assert any(expected_reason in message for message in render_telegram(digest))
    assert expected_reason in json.dumps([page.nodes for page in render_telegraph(digest)], ensure_ascii=False)
    assert expected_reason in site.pages["english"].read_text(encoding="utf-8")


@pytest.mark.parametrize("saved", [None, [], {"english": None},
    {"english": {"article_id": "a1", "reason_zh": DIGEST_REASON}},
    {"english": {"article_id": "a2", "reason_zh": ""}},
    {"english": {"article_id": "a2", "reason_zh": 42}},
    {"english": {"article_id": "a2", "reason_zh": INTERNAL_NOTE}},
    {"issue_date": "2026.09.26", "english": {"article_id": "a2", "reason_zh": DIGEST_REASON}},
    "invalid JSON"])
def test_unusable_saved_reason_runs_normal_pick_with_warning(analysis_config: Config, tmp_path: Path,
                                                            saved: object) -> None:
    source = issue([article("a1", words=800), article("a2", words=800)])
    history = [{"issue_date": source.issue_date, "article_id": "a2", "reason_zh": INTERNAL_NOTE}]
    path = issue_directory(analysis_config, source.issue_date) / "digest.json"
    if isinstance(saved, dict):
        save_json(path, {"issue_date": source.issue_date, **saved})
    elif saved == "invalid JSON":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("invalid JSON", encoding="utf-8")
    else:
        save_json(path, saved)
    client = FakeLLMClient(answer)
    digest = analyze_issue(source, analysis_config, client, workdir=tmp_path / "analysis", english_history=history)
    assert digest.english.article_id == "a1"
    assert digest.english.reason_zh == "結構清楚，單字實用。"
    assert sum(stage == "english_pick" for _, _, stage in client.calls) == 1
    assert any("缺少選文理由" in warning and "重新選文" in warning for warning in digest.warnings)
    assert "沿用本期" not in render_markdown(digest)
