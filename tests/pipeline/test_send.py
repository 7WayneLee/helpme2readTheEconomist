from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

import pytest

from econ_digest.commands import render, send
from econ_digest.cli import build_parser
from econ_digest.config import Config, SecretsConfig, TelegramConfig
from econ_digest.fetch import issue_directory
from econ_digest.models import Digest, save_json
from econ_digest.render import write_outputs
from econ_digest.state import load_state, run_lock
from econ_digest.telegram import TelegramError


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.documents: list[str | None] = []
        self.attempts = 0
        self.fail_message: int | None = None
        self.fail_document = False

    def send_message_safe(self, chat_id: str, html: str) -> int:
        self.attempts += 1
        if self.attempts == self.fail_message:
            raise TelegramError(503, "synthetic-secret-token must never appear in logs")
        self.messages.append(html)
        return self.attempts

    def send_document(self, chat_id: str, path: Path, *, caption_html: str | None = None) -> int:
        if self.fail_document:
            raise TelegramError(503, "synthetic failure")
        assert path.exists()
        self.documents.append(caption_html)
        return 100


@pytest.fixture
def prepared(delivery_config: Config, delivery_digest: Digest, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, FakeTelegram]:
    directory = issue_directory(delivery_config, delivery_digest.issue_date)
    save_json(directory / "digest.json", delivery_digest)
    write_outputs(delivery_digest, directory)
    save_json(directory / "telegram_messages.json", ["<b>First</b>", "Second", "Third"])
    client = FakeTelegram()
    monkeypatch.setattr(send, "TelegramClient", lambda *args, **kwargs: client)
    return directory, client


def test_resume_after_middle_failure(delivery_config: Config, delivery_digest: Digest,
                                     prepared: tuple[Path, FakeTelegram]) -> None:
    directory, client = prepared
    client.fail_message = 2
    with pytest.raises(TelegramError):
        send.send_digest(delivery_config)
    assert client.messages == ["<b>First</b>"]
    assert json.loads((directory / "telegram_progress.json").read_text())["next_message"] == 1
    assert load_state(delivery_config.paths.data_dir)["delivered"] == {}
    client.fail_message = None
    assert send.send_digest(delivery_config) == 0
    assert client.messages == ["<b>First</b>", "Second", "Third"]
    assert client.documents == ["完整報告（含英文選文原文）"]
    state = load_state(delivery_config.paths.data_dir)
    assert state["delivered"][delivery_digest.issue_date]["message_count"] == 3
    assert state["english_history"][0]["article_id"] == delivery_digest.english.article_id  # type: ignore[union-attr]


def test_resume_after_document_failure(delivery_config: Config, prepared: tuple[Path, FakeTelegram]) -> None:
    _, client = prepared
    client.fail_document = True
    with pytest.raises(TelegramError):
        send.send_digest(delivery_config)
    client.fail_document = False
    assert send.send_digest(delivery_config) == 0
    assert len(client.messages) == 3
    assert len(client.documents) == 1


def test_delivered_idempotency_and_force(delivery_config: Config, prepared: tuple[Path, FakeTelegram]) -> None:
    _, client = prepared
    assert send.send_digest(delivery_config) == 0
    assert send.send_digest(delivery_config) == 0
    assert len(client.messages) == 3
    assert send.send_digest(delivery_config, force=True) == 0
    assert len(client.messages) == 6 and len(client.documents) == 2
    assert len(load_state(delivery_config.paths.data_dir)["english_history"]) == 1


@pytest.mark.parametrize("secrets", [SecretsConfig(), SecretsConfig(telegram_bot_token="synthetic-secret-token"),
                                    SecretsConfig(telegram_chat_id="12345")])
def test_missing_secrets_exit_two(delivery_config: Config, prepared: tuple[Path, FakeTelegram],
                                 secrets: SecretsConfig, capsys: pytest.CaptureFixture[str]) -> None:
    _, client = prepared
    assert send.send_digest(replace(delivery_config, secrets=secrets)) == 2
    output = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN" in output and "telegram-setup" in output
    assert "synthetic-secret-token" not in output
    assert not client.messages


def test_dry_run_without_secrets(delivery_config: Config, prepared: tuple[Path, FakeTelegram],
                                capsys: pytest.CaptureFixture[str]) -> None:
    directory, client = prepared
    assert send.send_digest(replace(delivery_config, secrets=SecretsConfig()), dry_run=True) == 0
    assert "訊息 1/3" in capsys.readouterr().out
    assert not client.messages and not (directory / "telegram_progress.json").exists()
    assert not load_state(delivery_config.paths.data_dir)["delivered"]


def test_document_disabled(delivery_config: Config, prepared: tuple[Path, FakeTelegram]) -> None:
    _, client = prepared
    config = replace(delivery_config, telegram=TelegramConfig(send_report_file=False, delivery="messages"))
    assert send.send_digest(config) == 0
    assert len(client.messages) == 3 and not client.documents


def test_changed_content_requires_force(delivery_config: Config, prepared: tuple[Path, FakeTelegram]) -> None:
    directory, client = prepared
    client.fail_message = 2
    with pytest.raises(TelegramError):
        send.send_digest(delivery_config)
    save_json(directory / "telegram_messages.json", ["Changed", "Second", "Third"])
    client.fail_message = None
    with pytest.raises(ValueError, match="--force"):
        send.send_digest(delivery_config)
    assert send.send_digest(delivery_config, force=True) == 0
    assert client.messages == ["<b>First</b>", "Changed", "Second", "Third"]


def test_send_command_redacts_failure(delivery_config: Config, prepared: tuple[Path, FakeTelegram],
                                     capsys: pytest.CaptureFixture[str]) -> None:
    _, client = prepared
    client.fail_message = 1
    args = argparse.Namespace(issue="latest", force=False, dry_run=False)
    assert send.run(args, delivery_config) == 1
    assert "synthetic-secret-token" not in capsys.readouterr().out


def test_send_lock_held(delivery_config: Config, prepared: tuple[Path, FakeTelegram]) -> None:
    _, client = prepared
    with run_lock(delivery_config.paths.data_dir):
        assert send.run(argparse.Namespace(issue="latest", force=False, dry_run=False), delivery_config) == 0
    assert not client.messages


def test_render_command_saved_latest(delivery_config: Config, prepared: tuple[Path, FakeTelegram],
                                    capsys: pytest.CaptureFixture[str]) -> None:
    assert render.run(argparse.Namespace(issue="latest"), delivery_config) == 0
    output = capsys.readouterr().out
    assert "report.md" in output and "report.html" in output and "Telegram 訊息" in output


def test_saved_issue_path_validation(delivery_config: Config, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        render.saved_issue_directory(delivery_config)
    with pytest.raises(Exception, match="期別"):
        render.saved_issue_directory(delivery_config, "../../secrets")


def test_missing_secret_before_any_report_exists(delivery_config: Config) -> None:
    assert send.send_digest(replace(delivery_config, secrets=SecretsConfig())) == 2


def test_render_missing_digest_returns_one(delivery_config: Config) -> None:
    assert render.run(argparse.Namespace(issue="latest"), delivery_config) == 1


@pytest.mark.parametrize("dry_run", [False, True])
def test_pages_only_rejected_in_messages_mode(delivery_config: Config, dry_run: bool,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["send", "--pages-only", *(["--dry-run"] if dry_run else [])])
    assert send.run(args, replace(delivery_config, secrets=SecretsConfig())) == 2
    output = capsys.readouterr().out
    assert "--pages-only 僅適用於 Telegraph 模式" in output
    assert "telegram.delivery" in output
