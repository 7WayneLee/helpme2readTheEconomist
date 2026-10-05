from __future__ import annotations

from dataclasses import replace
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote
from urllib.request import OpenerDirector, Request

import pytest

from econ_digest.commands import send, telegraph_setup
from econ_digest.config import Config, SecretsConfig
from econ_digest.fetch import issue_directory
from econ_digest.models import Digest, save_json
from econ_digest.render.telegraph import original_text_messages
from econ_digest.state import load_state, save_state
from econ_digest.telegraph import TelegraphClient, TelegraphError
from econ_digest.telegram import TelegramClient, TelegramError

TOKEN = "synthetic-telegraph-send-secret"


class Response(io.BytesIO):
    status = 200


class DeliveryOpener(OpenerDirector):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict]] = []
        self.messages: list[dict] = []
        self.documents = 0
        self.creates = 0
        self.accounts = 0
        self.edits = 0
        self.attempts = 0
        self.fail_message: int | None = None
        self.fail_edit: int | None = None
        self.fail_document = False

    def open(self, request: Request, timeout: float = 30) -> Response:
        if request.full_url.startswith("https://api.telegra.ph/"):
            method = request.full_url.removeprefix("https://api.telegra.ph/")
            payload = {key: values[0] for key, values in parse_qs(request.data.decode(), keep_blank_values=True).items()}
            self.calls.append((method, payload))
            if method == "createAccount":
                self.accounts += 1
                result = {"access_token": TOKEN}
            else:
                assert payload["access_token"] == TOKEN
                if method == "createPage":
                    self.creates += 1
                    path = payload["title"] + "-10-05"
                else:
                    self.edits += 1
                    if self.edits == self.fail_edit:
                        return Response(json.dumps({"ok": False, "error": "CONTENT_TOO_BIG"}).encode())
                    path = unquote(method.removeprefix("editPage/"))
                result = {"path": path, "url": "https://telegra.ph/" + path}
        else:
            method = request.full_url.rsplit("/", 1)[-1]
            payload = json.loads(request.data) if method == "sendMessage" else {}
            self.calls.append((method, payload))
            if method == "sendMessage":
                self.attempts += 1
                if self.attempts == self.fail_message:
                    return Response(json.dumps({"ok": False, "error_code": 400, "description": "failure " + TOKEN}).encode())
                self.messages.append(payload)
            else:
                if self.fail_document:
                    return Response(json.dumps({"ok": False, "error_code": 400, "description": "failure " + TOKEN}).encode())
                self.documents += 1
            result = {"message_id": len(self.calls)}
        return Response(json.dumps({"ok": True, "result": result}).encode())


@pytest.fixture
def prepared_telegraph(delivery_config: Config, delivery_digest: Digest, monkeypatch: pytest.MonkeyPatch,
                       tmp_path: Path) -> tuple[Config, Path, DeliveryOpener]:
    config = replace(delivery_config, telegram=replace(delivery_config.telegram, delivery="telegraph", send_report_file=False),
                     secrets=replace(delivery_config.secrets, telegraph_access_token=TOKEN))
    directory = issue_directory(config, delivery_digest.issue_date)
    # Ensure more than one private text message for resume coverage.
    delivery_digest.issue.articles[0].paragraphs = ["A private synthetic original paragraph & <test>. " * 200, "Another paragraph."]
    save_json(directory / "digest.json", delivery_digest)
    (directory / "report.html").write_text("<html>合成完整報告</html>")
    opener = DeliveryOpener()
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(tmp_path / "env"))
    monkeypatch.setattr(send, "TelegraphClient", lambda token: TelegraphClient(token, opener=opener))
    monkeypatch.setattr(telegraph_setup, "TelegraphClient", lambda: TelegraphClient(opener=opener))
    monkeypatch.setattr(send, "TelegramClient", lambda token, **kw: TelegramClient(token, opener=opener, sleep=lambda _: None, **kw))
    return config, directory, opener


def test_telegraph_send_summary_private_original_and_state(prepared_telegraph: tuple, delivery_digest: Digest) -> None:
    config, directory, opener = prepared_telegraph
    assert send.send_digest(config) == 0
    assert opener.creates == 4 and opener.edits == 4 and opener.documents == 0
    assert len(opener.messages) == 1 + len(original_text_messages(delivery_digest))
    first = opener.messages[0]
    records = json.loads((directory / "telegraph_pages.json").read_text())
    assert first["link_preview_options"] == {"url": records[0]["url"], "prefer_large_media": False}
    assert first["text"].count("<a ") == 4
    for payload in opener.messages[1:]:
        assert "<blockquote expandable>" in payload["text"]
        assert payload["link_preview_options"] == {"is_disabled": True}
    assert not (directory / "telegram_messages.json").exists()
    progress = json.loads((directory / "telegram_progress.json").read_text())
    assert progress["pages_published"] and progress["next_message"] == len(opener.messages)
    state = load_state(config.paths.data_dir)
    assert state["delivered"][delivery_digest.issue_date]["message_count"] == len(opener.messages)
    assert state["english_history"][0]["article_id"] == delivery_digest.english.article_id


def test_resume_private_message_failure_does_not_publish_or_repeat_summary(prepared_telegraph: tuple) -> None:
    config, directory, opener = prepared_telegraph
    opener.fail_message = 2
    with pytest.raises(TelegramError):
        send.send_digest(config)
    assert len(opener.messages) == 1 and opener.creates == 4
    assert json.loads((directory / "telegram_progress.json").read_text())["next_message"] == 1
    assert not load_state(config.paths.data_dir)["delivered"]
    opener.fail_message = None
    assert send.send_digest(config) == 0
    assert opener.creates == 4 and opener.edits == 4
    assert sum("📰 <b>" in payload["text"] for payload in opener.messages) == 1


def test_resume_mid_publish_reuses_paths_and_only_sends_when_complete(prepared_telegraph: tuple) -> None:
    config, directory, opener = prepared_telegraph
    opener.fail_edit = 2
    with pytest.raises(TelegraphError):
        send.send_digest(config)
    assert not opener.messages and opener.creates == 4
    records = json.loads((directory / "telegraph_pages.json").read_text())
    assert not json.loads((directory / "telegram_progress.json").read_text())["pages_published"]
    opener.fail_edit = None
    assert send.send_digest(config) == 0
    assert json.loads((directory / "telegraph_pages.json").read_text()) == records
    assert opener.creates == 4


def test_force_edits_pages_and_resends_chat_only(prepared_telegraph: tuple) -> None:
    config, directory, opener = prepared_telegraph
    send.send_digest(config)
    count = len(opener.messages)
    send.send_digest(config)
    assert len(opener.messages) == count
    records = (directory / "telegraph_pages.json").read_text()
    assert send.send_digest(config, force=True) == 0
    assert len(opener.messages) == 2 * count
    assert opener.creates == 4 and opener.edits == 8
    assert (directory / "telegraph_pages.json").read_text() == records
    assert len(load_state(config.paths.data_dir)["english_history"]) == 1


def test_changed_digest_refuses_resume_until_force(prepared_telegraph: tuple, delivery_digest: Digest) -> None:
    config, directory, opener = prepared_telegraph
    opener.fail_message = 2
    with pytest.raises(TelegramError):
        send.send_digest(config)
    delivery_digest.summaries[delivery_digest.issue.articles[0].id].summary_zh = "更新後的合成摘要"
    save_json(directory / "digest.json", delivery_digest)
    opener.fail_message = None
    with pytest.raises(ValueError, match="--force"):
        send.send_digest(config)
    assert opener.edits == 4 and len(opener.messages) == 1
    assert send.send_digest(config, force=True) == 0
    assert opener.creates == 4 and opener.edits == 8


def test_auto_setup_missing_access_token(prepared_telegraph: tuple, monkeypatch: pytest.MonkeyPatch,
                                         tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config, _, opener = prepared_telegraph
    config = replace(config, secrets=replace(config.secrets, telegraph_access_token=None))
    assert send.send_digest(config) == 0
    assert opener.accounts == 1
    assert (tmp_path / "env").read_text() == "TELEGRAPH_ACCESS_TOKEN=" + TOKEN + "\n"
    assert TOKEN not in capsys.readouterr().out


def test_document_opt_in_resumes_after_failure(prepared_telegraph: tuple) -> None:
    config, directory, opener = prepared_telegraph
    config = replace(config, telegram=replace(config.telegram, send_report_file=True))
    opener.fail_document = True
    with pytest.raises(TelegramError):
        send.send_digest(config)
    count = len(opener.messages)
    opener.fail_document = False
    assert send.send_digest(config) == 0
    assert len(opener.messages) == count and opener.documents == 1 and opener.edits == 4


def test_dry_run_without_secrets_no_network_or_progress(prepared_telegraph: tuple, capsys: pytest.CaptureFixture[str]) -> None:
    config, directory, opener = prepared_telegraph
    config = replace(config, secrets=SecretsConfig())
    # Delivered issues still allow an offline preview without --force.
    state = load_state(config.paths.data_dir)
    state["delivered"]["2026.10.03"] = {"delivered_at": "synthetic", "message_count": 16}
    save_state(config.paths.data_dir, state)
    assert send.send_digest(config, dry_run=True) == 0
    output = capsys.readouterr().out
    assert output.count("位元組") == 4 and "① 本週導讀" in output and "④ 英文學習" in output
    assert "原文（點開）" in output and "本週導讀：要聞與台灣" in output
    assert not opener.calls
    assert not (directory / "telegraph_pages.json").exists()
    assert not (directory / "telegram_progress.json").exists()
