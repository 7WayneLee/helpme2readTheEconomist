from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import stat

import pytest

from econ_digest.commands import telegram_setup
from econ_digest.config import Config, SecretsConfig


@pytest.fixture
def fake_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, list[str]]:
    path = tmp_path / "private" / "env"
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(path))
    sent: list[str] = []

    class Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def get_me(self) -> dict[str, str]:
            return {"username": "synthetic_digest_bot"}

        def get_updates(self) -> list[dict[str, object]]:
            return [{"update_id": 1, "message": {"chat": {"id": 54321, "type": "private", "first_name": "Synthetic reader"}}}]

        def send_message_safe(self, chat_id: str, text: str) -> int:
            sent.append(text)
            return 1

    monkeypatch.setattr(telegram_setup, "TelegramClient", Client)
    return path, sent


def test_discovery_preserves_env_and_mode(delivery_config: Config, fake_setup: tuple[Path, list[str]],
                                         capsys: pytest.CaptureFixture[str]) -> None:
    path, sent = fake_setup
    path.parent.mkdir()
    original = "# private secrets\nTELEGRAM_BOT_TOKEN=synthetic-secret-token\nOTHER_SETTING=keep this\nTELEGRAM_CHAT_ID=1\n"
    path.write_text(original)
    path.chmod(0o644)
    assert telegram_setup.run(argparse.Namespace(chat_id=None, test=True, wait=0), delivery_config) == 0
    assert path.read_text() == original.replace("TELEGRAM_CHAT_ID=1", "TELEGRAM_CHAT_ID=54321")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert sent == ["✅ 經濟學人導讀機器人設定完成"]
    output = capsys.readouterr().out
    assert "@synthetic_digest_bot" in output and "54321" in output
    assert "synthetic-secret-token" not in output


def test_explicit_id_no_poll(delivery_config: Config, fake_setup: tuple[Path, list[str]], monkeypatch: pytest.MonkeyPatch) -> None:
    path, sent = fake_setup
    monkeypatch.setattr(telegram_setup, "discover_private_chats", lambda client: pytest.fail("must not poll"))
    assert telegram_setup.run(argparse.Namespace(chat_id="6789", test=False, wait=120), delivery_config) == 0
    assert path.read_text() == "TELEGRAM_CHAT_ID=6789\n" and not sent
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_poll_timeout(delivery_config: Config, fake_setup: tuple[Path, list[str]], monkeypatch: pytest.MonkeyPatch) -> None:
    path, _ = fake_setup
    monkeypatch.setattr(telegram_setup, "discover_private_chats", lambda client: [])
    assert telegram_setup.run(argparse.Namespace(chat_id=None, test=False, wait=0), delivery_config) == 2
    assert not path.exists()


def test_multiple_chats_need_explicit_id(delivery_config: Config, fake_setup: tuple[Path, list[str]],
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    path, _ = fake_setup
    monkeypatch.setattr(telegram_setup, "discover_private_chats", lambda client: [{"chat_id": 1}, {"chat_id": 2}])
    assert telegram_setup.run(argparse.Namespace(chat_id=None, test=False, wait=0), delivery_config) == 2
    assert not path.exists()


def test_missing_bot_token(delivery_config: Config, fake_setup: tuple[Path, list[str]]) -> None:
    assert telegram_setup.run(argparse.Namespace(chat_id=None, test=False, wait=0), replace(delivery_config, secrets=SecretsConfig())) == 2


@pytest.mark.parametrize("value", ["abc", "12\nTELEGRAM_BOT_TOKEN=evil", "", "12 34"])
def test_env_rejects_invalid_chat_id(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError):
        telegram_setup.update_chat_id(tmp_path / "env", value)


def test_env_append_preserves_last_line_and_deduplicates(tmp_path: Path) -> None:
    path = tmp_path / "env"
    path.write_text("KEEP=yes")
    telegram_setup.update_chat_id(path, "5")
    assert path.read_text() == "KEEP=yes\nTELEGRAM_CHAT_ID=5\n"
    path.write_text("TELEGRAM_CHAT_ID=1\nKEEP=yes\nTELEGRAM_CHAT_ID=2\n")
    telegram_setup.update_chat_id(path, "6")
    assert path.read_text() == "TELEGRAM_CHAT_ID=6\nKEEP=yes\n"
