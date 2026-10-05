from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from econ_digest import pipeline
from econ_digest.config import Config, SecretsConfig, TelegramConfig
from econ_digest.fetch import issue_directory
from econ_digest.models import Digest, save_json
from econ_digest.state import load_state, run_lock, save_state


@pytest.fixture
def fake_stages(delivery_config: Config, delivery_digest: Digest, synthetic_epub: Path,
                monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    class Fetcher:
        def __init__(self, config: Config) -> None:
            pass

        def resolve_issue(self, spec: str) -> str:
            calls.append("resolve")
            return delivery_digest.issue_date

        def download_issue(self, date: str) -> Path:
            calls.append("fetch")
            return synthetic_epub

    def parse(*args: object) -> object:
        calls.append("parse")
        return delivery_digest.issue

    def analyze(*args: object) -> Digest:
        calls.append("analyze")
        return delivery_digest

    def send(config: Config, date: str, **kwargs: object) -> int:
        calls.append("send")
        state = load_state(config.paths.data_dir)
        state["delivered"][date] = {"delivered_at": "synthetic timestamp", "message_count": 3}
        save_state(config.paths.data_dir, state)
        return 0

    monkeypatch.setattr(pipeline, "Fetcher", Fetcher)
    monkeypatch.setattr(pipeline, "parse_epub", parse)
    monkeypatch.setattr(pipeline, "_analyze", analyze)
    monkeypatch.setattr(pipeline, "_send", send)
    return calls


def test_run_success(delivery_config: Config, delivery_digest: Digest, fake_stages: list[str]) -> None:
    assert pipeline.run_pipeline(delivery_config) == 0
    assert fake_stages == ["resolve", "fetch", "parse", "analyze", "send"]
    directory = issue_directory(delivery_config, delivery_digest.issue_date)
    assert all((directory / name).exists() for name in ("digest.json", "issue.json", "report.md", "report.html", "telegram_messages.json"))
    state = load_state(delivery_config.paths.data_dir)
    assert state["last_run"]["outcome"] == "success"
    assert state["last_run"]["finished_at"] and state["last_run"]["error"] is None
    assert delivery_digest.issue_date in state["delivered"]


def test_nothing_new(delivery_config: Config, delivery_digest: Digest, fake_stages: list[str]) -> None:
    state = load_state(delivery_config.paths.data_dir)
    state["delivered"][delivery_digest.issue_date] = {"delivered_at": "synthetic timestamp", "message_count": 2}
    save_state(delivery_config.paths.data_dir, state)
    logs: list[str] = []
    assert pipeline.run_pipeline(delivery_config, log=logs.append) == 0
    assert fake_stages == ["resolve"] and "沒有新的一期" in logs
    assert load_state(delivery_config.paths.data_dir)["last_run"]["outcome"] == "nothing_new"


@pytest.mark.parametrize("options", [{"no_send": True}, {"dry_run": True}])
def test_report_without_delivery(delivery_config: Config, fake_stages: list[str], options: dict[str, bool]) -> None:
    logs: list[str] = []
    assert pipeline.run_pipeline(delivery_config, log=logs.append, **options) == 0
    assert "send" not in fake_stages
    assert any("報告已產生" in line for line in logs)
    assert not load_state(delivery_config.paths.data_dir)["delivered"]


@pytest.mark.parametrize("config_change", ["disabled", "missing_secrets"])
def test_unconfigured_delivery_is_success(delivery_config: Config, fake_stages: list[str], config_change: str) -> None:
    config = replace(delivery_config, telegram=TelegramConfig(enabled=False)) if config_change == "disabled" else replace(delivery_config, secrets=SecretsConfig())
    assert pipeline.run_pipeline(config) == 0
    assert "send" not in fake_stages


def test_cache_and_reanalyze(delivery_config: Config, delivery_digest: Digest, fake_stages: list[str]) -> None:
    directory = issue_directory(delivery_config, delivery_digest.issue_date)
    save_json(directory / "digest.json", delivery_digest)
    assert pipeline.run_pipeline(delivery_config, no_send=True) == 0
    assert fake_stages == ["resolve"]
    fake_stages.clear()
    assert pipeline.run_pipeline(delivery_config, no_send=True, reanalyze=True) == 0
    assert fake_stages == ["resolve", "fetch", "parse", "analyze"]


def test_force_delivered_issue(delivery_config: Config, delivery_digest: Digest, fake_stages: list[str]) -> None:
    state = load_state(delivery_config.paths.data_dir)
    state["delivered"][delivery_digest.issue_date] = {"delivered_at": "synthetic timestamp", "message_count": 2}
    save_state(delivery_config.paths.data_dir, state)
    assert pipeline.run_pipeline(delivery_config, force=True) == 0
    assert "send" in fake_stages


def test_lock_held_skips(delivery_config: Config, fake_stages: list[str]) -> None:
    with run_lock(delivery_config.paths.data_dir):
        assert pipeline.run_pipeline(delivery_config) == 0
    assert not fake_stages


def test_analysis_failure_notice_once_per_day(delivery_config: Config, delivery_digest: Digest,
                                             fake_stages: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    notices: list[str] = []

    class AnalysisError(Exception):
        pass

    def fail(*args: object) -> Digest:
        raise AnalysisError("synthetic-secret-token in an unsafe error")

    class Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def send_message_safe(self, chat_id: str, text: str) -> int:
            notices.append(text)
            return 1

    monkeypatch.setattr(pipeline, "_analyze", fail)
    monkeypatch.setattr(pipeline, "TelegramClient", Client)
    logs: list[str] = []
    assert pipeline.run_pipeline(delivery_config, log=logs.append) == 1
    assert pipeline.run_pipeline(delivery_config, log=logs.append) == 1
    assert len(notices) == 1 and "（AnalysisError）" in notices[0]
    assert "synthetic-secret-token" not in "".join(logs + notices)
    state = load_state(delivery_config.paths.data_dir)
    assert state["last_run"]["outcome"] == "failed" and state["last_run"]["error"] == "AnalysisError"
    state["error_notices"][delivery_digest.issue_date] = "1900-01-01"  # type: ignore[typeddict-item]
    save_state(delivery_config.paths.data_dir, state)
    assert pipeline.run_pipeline(delivery_config) == 1
    assert len(notices) == 2


def test_send_failure_returns_one(delivery_config: Config, fake_stages: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "_send", lambda *args, **kwargs: 1)
    monkeypatch.setattr(pipeline, "_error_notice", lambda *args, **kwargs: None)
    assert pipeline.run_pipeline(delivery_config) == 1
    assert load_state(delivery_config.paths.data_dir)["last_run"]["outcome"] == "failed"


def test_run_builds_site_and_performs_backup_after_build(delivery_config, fake_stages, monkeypatch):
    from econ_digest.config import BackupConfig
    config = replace(delivery_config, backup=BackupConfig(True, "https://example.invalid/private.git"))
    calls = []
    def backup(root, settings, date, data, **kw):
        assert (root / "2026-10-03/index.html").is_file()
        calls.append((date, kw))
    monkeypatch.setattr(pipeline, "backup_output", backup)
    assert pipeline.run_pipeline(config, no_send=True) == 0
    assert calls[0][0] == "2026.10.03" and calls[0][1]["dry_run"] is False
    assert "send" not in fake_stages


def test_run_dry_run_only_describes_backup(delivery_config, fake_stages, monkeypatch):
    from econ_digest.config import BackupConfig
    config = replace(delivery_config, backup=BackupConfig(True, "https://example.invalid/private.git"))
    calls = []
    monkeypatch.setattr(pipeline, "backup_output", lambda *args, **kw: calls.append(kw))
    monkeypatch.setattr(pipeline, "build_site", lambda *a, **kw: pytest.fail("dry run must not build the private site"))
    assert pipeline.run_pipeline(config, dry_run=True) == 0
    assert calls[0]["dry_run"] is True
