from __future__ import annotations

from dataclasses import replace
from email import policy
from email.parser import BytesParser
import io
import json
import shutil
from pathlib import Path
from urllib.parse import parse_qs, unquote
from urllib.request import OpenerDirector, Request

import pytest

from econ_digest.commands import send, telegraph_setup
from econ_digest.cli import build_parser
from econ_digest.config import Config, SecretsConfig, SiteConfig
from econ_digest.fetch import issue_directory
from econ_digest.models import Digest, save_json
from econ_digest.render.telegraph import caption_length, original_text_messages
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
        self.photos: list[dict] = []
        self.creates = 0
        self.accounts = 0
        self.edits = 0
        self.attempts = 0
        self.fail_message: int | None = None
        self.fail_edit: int | None = None
        self.fail_document = False
        self.fail_photo = False

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
            if method == "sendMessage":
                payload = json.loads(request.data)
            else:
                header = request.get_header("Content-type")
                multipart = BytesParser(policy=policy.default).parsebytes(
                    f"Content-Type: {header}\r\nMIME-Version: 1.0\r\n\r\n".encode() + request.data)
                payload = {part.get_param("name", header="content-disposition"):
                           part.get_payload(decode=True) if part.get_filename() else part.get_payload(decode=True).decode()
                           for part in multipart.iter_parts()}
            self.calls.append((method, payload))
            if method == "sendMessage":
                self.attempts += 1
                if self.attempts == self.fail_message:
                    return Response(json.dumps({"ok": False, "error_code": 400, "description": "failure " + TOKEN}).encode())
                self.messages.append(payload)
            elif method == "sendPhoto":
                if self.fail_photo:
                    return Response(json.dumps({"ok": False, "error_code": 400, "description": "synthetic photo failure"}).encode())
                self.photos.append(payload)
            else:
                if self.fail_document:
                    return Response(json.dumps({"ok": False, "error_code": 400, "description": "failure " + TOKEN}).encode())
                self.documents += 1
            result = {"message_id": len(self.calls)}
        return Response(json.dumps({"ok": True, "result": result}).encode())


@pytest.fixture
def prepared_telegraph(delivery_config: Config, delivery_digest: Digest, monkeypatch: pytest.MonkeyPatch,
                       tmp_path: Path) -> tuple[Config, Path, DeliveryOpener]:
    config = replace(delivery_config, telegram=replace(delivery_config.telegram, delivery="telegraph", send_report_file=False, original_text_messages=True),
                     secrets=replace(delivery_config.secrets, telegraph_access_token=TOKEN))
    directory = issue_directory(config, delivery_digest.issue_date)
    # Ensure more than one private text message for resume coverage.
    delivery_digest.issue.articles[0].paragraphs = ["A private synthetic original paragraph & <test>. " * 200, "Another paragraph."]
    extra = replace(delivery_digest.issue.articles[0], id="international-example", title="Synthetic international story", order=10)
    delivery_digest.issue.articles.append(extra)
    base = delivery_digest.classifications[delivery_digest.issue.articles[0].id]
    delivery_digest.classifications[extra.id] = replace(base, article_id=extra.id, category="intl.us", title_zh="合成國際故事")
    delivery_digest.summaries[extra.id] = replace(delivery_digest.summaries[base.article_id], article_id=extra.id)
    save_json(directory / "digest.json", delivery_digest)
    (directory / "report.html").write_text("<html>合成完整報告</html>")
    opener = DeliveryOpener()
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(tmp_path / "env"))
    monkeypatch.setattr(send, "TelegraphClient", lambda token: TelegraphClient(token, opener=opener))
    monkeypatch.setattr(telegraph_setup, "TelegraphClient", lambda: TelegraphClient(opener=opener))
    monkeypatch.setattr(send, "TelegramClient", lambda token, **kw: TelegramClient(token, opener=opener, sleep=lambda _: None, **kw))
    return config, directory, opener


@pytest.fixture
def prepared_photo(prepared_telegraph: tuple, illustrated_epub: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    config, directory, opener = prepared_telegraph
    config = replace(config, telegram=replace(config.telegram, send_report_file=True, cover_photo=True),
                     site=SiteConfig(True, "https://site.example", "example-host", "/srv/example"))
    from econ_digest.site.publish import PublishedSite
    monkeypatch.setattr(send, "publish_site", lambda site, *args, **kwargs: PublishedSite(
        "https://site.example/2026-10-03/index.html", "https://site.example/covers/cover.jpg" if site.cover else None))
    shutil.copyfile(illustrated_epub, directory / "TheEconomist.2026.10.03.epub")
    return config, directory, opener


def test_photo_summary_originals_document_order(prepared_photo: tuple, synthetic_pngs: dict[str, bytes]) -> None:
    config, directory, opener = prepared_photo
    assert send.send_digest(config) == 0
    methods = [method for method, _ in opener.calls if method.startswith("send")]
    digest = Digest.from_dict(json.loads((directory / "digest.json").read_text()))
    assert methods == ["sendPhoto", *["sendMessage"] * len(original_text_messages(digest)), "sendDocument"]
    caption = opener.photos[0]["caption"]
    assert opener.photos[0]["photo"] == synthetic_pngs["cover"] and opener.photos[0]["parse_mode"] == "HTML"
    assert caption_length(caption) <= 1024 and caption.count('<a href="') == 5
    assert "原文（點開）" in opener.messages[0]["text"]
    assert opener.calls[-1][1]["caption"] == "完整報告（含插圖與英文選文原文）"


@pytest.mark.parametrize("failure", ["photo", "original", "document"])
def test_photo_resume_does_not_repeat_completed_steps(prepared_photo: tuple, failure: str) -> None:
    config, directory, opener = prepared_photo
    opener.fail_photo = failure == "photo"
    opener.fail_message = 1 if failure == "original" else None
    opener.fail_document = failure == "document"
    with pytest.raises(TelegramError):
        send.send_digest(config)
    progress = json.loads((directory / "telegram_progress.json").read_text())
    assert progress["next_message"] == (0 if failure == "photo" else 1 if failure == "original" else 5)
    originals_sent = len(opener.messages)
    opener.fail_photo = opener.fail_document = False
    opener.fail_message = None
    assert send.send_digest(config) == 0
    assert len(opener.photos) == 1 and opener.documents == 1
    if failure == "document":
        assert len(opener.messages) == originals_sent
    assert opener.creates == 4 and opener.edits == 4


def test_changed_cover_rejects_resume(prepared_photo: tuple, illustrated_epub: Path, synthetic_pngs: dict[str, bytes]) -> None:
    from zipfile import ZipFile
    config, directory, opener = prepared_photo
    opener.fail_message = 1
    with pytest.raises(TelegramError):
        send.send_digest(config)
    path = directory / "TheEconomist.2026.10.03.epub"
    with ZipFile(path) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    contents["EPUB/static_images/cover.png"] = synthetic_pngs["head"]
    with ZipFile(path, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    with pytest.raises(ValueError, match="已變更"):
        send.send_digest(config)
    assert len(opener.photos) == 1


@pytest.mark.parametrize("fallback", ["missing-cover", "disabled", "messages"])
def test_cover_fallback_and_messages_mode(prepared_photo: tuple, fallback: str) -> None:
    from zipfile import ZipFile
    from econ_digest.render import render_telegram
    config, directory, opener = prepared_photo
    if fallback == "missing-cover":
        path = directory / "TheEconomist.2026.10.03.epub"
        with ZipFile(path) as source:
            contents = {name: source.read(name) for name in source.namelist() if not name.endswith("cover.png")}
        with ZipFile(path, "w") as archive:
            for name, data in contents.items():
                archive.writestr(name, data)
    elif fallback == "disabled":
        config = replace(config, telegram=replace(config.telegram, cover_photo=False))
    else:
        config = replace(config, telegram=replace(config.telegram, delivery="messages"))
        digest = Digest.from_dict(json.loads((directory / "digest.json").read_text()))
        save_json(directory / "telegram_messages.json", render_telegram(digest))
    assert send.send_digest(config) == 0
    assert not opener.photos and opener.documents == 1
    if fallback != "messages":
        assert opener.messages[0]["text"].count('<a href="') == 5
        assert "url" in opener.messages[0]["link_preview_options"]


def test_long_caption_photo_then_summary_with_preview(prepared_photo: tuple) -> None:
    config, directory, opener = prepared_photo
    digest = Digest.from_dict(json.loads((directory / "digest.json").read_text()))
    digest.issue.articles[0].kind = "leader"
    digest.issue.articles[0].is_cover = True
    digest.classifications[digest.issue.articles[0].id].title_zh = "合成長標題" * 210
    save_json(directory / "digest.json", digest)
    # A failure after the photo proves the extra summary is an independent resume step.
    opener.fail_message = 1
    with pytest.raises(TelegramError):
        send.send_digest(config)
    assert len(opener.photos) == 1 and opener.photos[0]["caption"].startswith("<b>經濟學人導讀")
    opener.fail_message = None
    assert send.send_digest(config) == 0
    assert len(opener.photos) == 1
    assert "合成長標題" in opener.messages[0]["text"] and opener.messages[0]["text"].count('<a href="') == 5
    assert "url" in opener.messages[0]["link_preview_options"]
    assert "原文（點開）" in opener.messages[1]["text"]


def test_photo_dry_run_shows_sequence_without_network(prepared_photo: tuple, capsys: pytest.CaptureFixture[str]) -> None:
    config, directory, opener = prepared_photo
    assert send.send_digest(replace(config, secrets=SecretsConfig()), dry_run=True) == 0
    output = capsys.readouterr().out
    assert output.index("封面照片") < output.index("原文（點開）") < output.index("--- 文件：")
    assert "圖說可見長度" in output and "/1024 個 UTF-16 單位" in output
    assert not opener.calls and not (directory / "telegram_progress.json").exists()


def test_telegraph_send_summary_private_original_and_state(prepared_telegraph: tuple, delivery_digest: Digest) -> None:
    config, directory, opener = prepared_telegraph
    assert send.send_digest(config) == 0
    assert opener.creates == 4 and opener.edits == 4 and opener.documents == 1
    assert len(opener.messages) == 1 + len(original_text_messages(delivery_digest))
    first = opener.messages[0]
    records = json.loads((directory / "telegraph_pages.json").read_text())
    assert first["link_preview_options"] == {"url": records[0]["url"], "prefer_large_media": True}
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
    assert output.count("位元組") == 4 and "本週導讀" in output and "英文學習" in output
    assert "原文（點開）" in output and "本週導讀" in output
    assert not opener.calls
    assert not (directory / "telegraph_pages.json").exists()
    assert not (directory / "telegram_progress.json").exists()


@pytest.mark.parametrize("delivered,force", [(False, False), (True, False), (True, True)])
def test_pages_only_edits_in_place_preserves_state_and_chat_progress(
        prepared_telegraph: tuple, delivery_digest: Digest, monkeypatch: pytest.MonkeyPatch,
        delivered: bool, force: bool) -> None:
    config, directory, opener = prepared_telegraph
    if delivered:
        assert send.send_digest(config) == 0
    else:
        opener.fail_message = 2
        with pytest.raises(TelegramError):
            send.send_digest(config)
        opener.fail_message = None
    # Preserve even unrelated run/history fields exactly as stored.
    state = load_state(config.paths.data_dir)
    state["last_run"]["outcome"] = "synthetic-existing-run"
    save_state(config.paths.data_dir, state)
    state_path = config.paths.data_dir / "state.json"
    state_before = state_path.read_bytes()
    progress_path = directory / "telegram_progress.json"
    progress_before = progress_path.read_bytes()
    pages_path = directory / "telegraph_pages.json"
    pages_before = pages_path.read_bytes()
    paths = [record["path"] for record in json.loads(pages_before)]

    delivery_digest.summaries[delivery_digest.issue.articles[0].id].summary_zh = "更正後的頁面摘要"
    save_json(directory / "digest.json", delivery_digest)
    (directory / "report.html").unlink()
    config = replace(config, secrets=SecretsConfig(telegraph_access_token=TOKEN),
                     telegram=replace(config.telegram, send_report_file=True))
    opener.calls.clear()

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("僅更新頁面時不得建立 Telegram 客戶端或產生聊天訊息")

    monkeypatch.setattr(send, "TelegramClient", forbidden)
    monkeypatch.setattr(send, "summary_message", forbidden)
    monkeypatch.setattr(send, "original_text_messages", forbidden)
    args = build_parser().parse_args(["send", "--issue", delivery_digest.issue_date, "--pages-only",
                                      *(["--force"] if force else [])])
    assert send.run(args, config) == 0
    assert [method for method, _ in opener.calls] == ["editPage/" + path for path in paths]
    assert "更正後的頁面摘要" in opener.calls[2][1]["content"]
    assert state_path.read_bytes() == state_before
    assert progress_path.read_bytes() == progress_before
    assert pages_path.read_bytes() == pages_before


def test_pages_only_creates_only_missing_pages_without_state_or_progress(prepared_telegraph: tuple) -> None:
    config, directory, opener = prepared_telegraph
    pages_path = directory / "telegraph_pages.json"
    known = [{"key": "weekly:1", "path": "synthetic-stored-path", "url": "https://telegra.ph/synthetic-stored-path"}]
    save_json(pages_path, known)
    config = replace(config, secrets=SecretsConfig(telegraph_access_token=TOKEN))
    assert send.send_digest(config, pages_only=True) == 0
    assert opener.creates == 3 and opener.edits == 4
    assert not opener.messages and not opener.documents
    assert all(method in ("createPage",) or method.startswith("editPage/") for method, _ in opener.calls)
    assert json.loads(pages_path.read_text())[0] == known[0]
    assert not (directory / "telegram_progress.json").exists()
    assert not (config.paths.data_dir / "state.json").exists()
    opener.calls.clear()
    assert send.send_digest(config, pages_only=True) == 0
    assert opener.creates == 3 and opener.edits == 8
    assert all(method.startswith("editPage/") for method, _ in opener.calls)


def test_pages_only_adds_taiwan_reuses_old_paths_and_edits_in_reading_order(prepared_telegraph):
    config, directory, opener = prepared_telegraph
    assert send.send_digest(config) == 0
    records = json.loads((directory / "telegraph_pages.json").read_text())
    progress = (directory / "telegram_progress.json").read_bytes()
    state = (config.paths.data_dir / "state.json").read_bytes()
    digest = Digest.from_dict(json.loads((directory / "digest.json").read_text()))
    base = digest.issue.articles[0]
    added = replace(base, id="taiwan-example", order=20, title="Synthetic Taiwan story")
    digest.issue.articles.append(added)
    digest.classifications[added.id] = replace(digest.classifications[base.id], article_id=added.id, taiwan_level=3,
                                               title_zh="合成台灣故事", taiwan_link="合成產業關聯")
    digest.summaries[added.id] = replace(digest.summaries[base.id], article_id=added.id)
    save_json(directory / "digest.json", digest)
    opener.calls.clear()
    assert send.send_digest(config, pages_only=True) == 0
    extended = json.loads((directory / "telegraph_pages.json").read_text())
    assert extended[:4] == records and extended[4]["key"] == "taiwan:1"
    assert opener.creates == 5
    expected = [records[0], extended[4], *records[1:]]
    edits = [(method, payload) for method, payload in opener.calls if method.startswith("editPage/")]
    assert [method for method, _ in edits] == ["editPage/" + record["path"] for record in expected]
    assert [payload["title"].split("｜")[-1] for _, payload in edits] == ["本週導讀", "台灣", "國際", "財經・科技・文化", "英文學習"]
    assert "合成台灣故事" not in edits[0][1]["content"] and "合成台灣故事" in edits[1][1]["content"]
    assert (directory / "telegram_progress.json").read_bytes() == progress
    assert (config.paths.data_dir / "state.json").read_bytes() == state
    opener.calls.clear()
    assert send.send_digest(config, pages_only=True) == 0
    assert opener.creates == 5 and json.loads((directory / "telegraph_pages.json").read_text()) == extended
    assert all(method.startswith("editPage/") for method, _ in opener.calls)


@pytest.mark.parametrize("existing_pages", [False, True])
def test_pages_only_dry_run_lists_only_page_titles_and_sizes(
        prepared_telegraph: tuple, capsys: pytest.CaptureFixture[str], existing_pages: bool) -> None:
    config, directory, opener = prepared_telegraph
    if existing_pages:
        assert send.send_digest(config) == 0
    snapshot = {path: path.read_bytes() for path in directory.glob("*.json")}
    state_path = config.paths.data_dir / "state.json"
    state_before = state_path.read_bytes() if state_path.exists() else None
    opener.calls.clear()
    capsys.readouterr()
    args = build_parser().parse_args(["send", "--issue", "2026.10.03", "--pages-only", "--dry-run"])
    assert send.run(args, replace(config, secrets=SecretsConfig())) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.endswith(" 位元組")]
    assert len(lines) == 4
    assert all(line.startswith("經濟學人導讀 2026/10/03｜") and line.endswith(" 位元組") for line in lines)
    assert not opener.calls
    assert {path: path.read_bytes() for path in directory.glob("*.json")} == snapshot
    assert (state_path.read_bytes() if state_path.exists() else None) == state_before


def test_pages_only_retry_reuses_allocated_paths_after_failure(prepared_telegraph: tuple) -> None:
    config, directory, opener = prepared_telegraph
    opener.fail_edit = 2
    with pytest.raises(TelegraphError):
        send.send_digest(config, pages_only=True)
    records = (directory / "telegraph_pages.json").read_bytes()
    assert opener.creates == 4 and not opener.messages and not opener.documents
    opener.fail_edit = None
    assert send.send_digest(config, pages_only=True) == 0
    assert opener.creates == 4 and opener.edits == 6
    assert (directory / "telegraph_pages.json").read_bytes() == records
    assert not (directory / "telegram_progress.json").exists()
    assert not (config.paths.data_dir / "state.json").exists()


def test_new_default_one_summary_large_cover_and_private_link(prepared_photo):
    config, directory, opener = prepared_photo
    config = replace(config, telegram=replace(config.telegram, cover_photo=False, original_text_messages=False, send_report_file=False))
    assert send.send_digest(config) == 0
    assert len(opener.messages) == 1 and not opener.photos and not opener.documents
    message = opener.messages[0]
    assert "🔒 圖文完整版（需帳密）：" in message["text"]
    assert "https://site.example/2026-10-03/index.html" in message["text"]
    assert message["link_preview_options"]["prefer_large_media"] is True
    assert "原文（點開）" not in message["text"] and "①" not in message["text"]
    assert (config.paths.output_dir / "2026-10-03/TheEconomist.2026.10.03.epub").exists()
    pages = [payload for method, payload in opener.calls if method.startswith("editPage/")]
    for page in pages:
        nodes = json.loads(page["content"])
        assert nodes[0]["tag"] == "figure"
        assert nodes[0]["children"][0]["attrs"]["src"] == "https://site.example/covers/cover.jpg"


@pytest.mark.parametrize("reason", ["disabled", "publish-failed"])
def test_new_fallback_omits_site_and_cover_sends_one_message_and_report(prepared_photo, monkeypatch, reason):
    config, directory, opener = prepared_photo
    config = replace(config, telegram=replace(config.telegram, cover_photo=True, original_text_messages=False, send_report_file=False))
    if reason == "disabled":
        config = replace(config, site=SiteConfig())
    monkeypatch.setattr(send, "publish_site", lambda *args, **kw: None)
    assert send.send_digest(config) == 0
    assert len(opener.messages) == 1 and opener.documents == 1 and not opener.photos
    assert "site.example" not in opener.messages[0]["text"]
    assert "🔒" not in opener.messages[0]["text"]
    assert all('"tag": "figure"' not in payload["content"] for method, payload in opener.calls if method.startswith("editPage/"))


def test_channel_one_summary_without_private_url_and_resume_no_double_post(prepared_photo):
    config, directory, opener = prepared_photo
    config = replace(config, telegram=replace(config.telegram, cover_photo=False, original_text_messages=False, send_report_file=False),
                     secrets=replace(config.secrets, telegram_channel_id="-100123456789"))
    opener.fail_message = 2
    with pytest.raises(TelegramError):
        send.send_digest(config)
    assert len(opener.messages) == 1 and opener.messages[0]["chat_id"] == config.secrets.telegram_chat_id
    assert not json.loads((directory / "telegram_progress.json").read_text())["channel_sent"]
    opener.fail_message = None
    assert send.send_digest(config) == 0
    assert len(opener.messages) == 2
    private, channel = opener.messages
    assert channel["chat_id"] == "-100123456789"
    assert "site.example" in private["text"] and "site.example" not in channel["text"]
    assert "🔒" not in channel["text"]
    for message in (private, channel):
        assert "與台灣相關" not in message["text"] and "英文選文：" not in message["text"]
        assert "共 2 篇文章" in message["text"] and "社論" not in message["text"]
        labels = ["本週導讀", "國際", "財經・科技・文化", "英文學習"]
        assert [message["text"].index('>' + label + '</a>') for label in labels] == sorted(
            message["text"].index('>' + label + '</a>') for label in labels)
    assert channel["link_preview_options"] == private["link_preview_options"]
    assert json.loads((directory / "telegram_progress.json").read_text())["channel_sent"]
    assert not opener.documents and not opener.photos
    assert send.send_digest(config) == 0 and len(opener.messages) == 2


def test_channel_fallback_never_receives_document_or_originals(prepared_telegraph):
    config, _, opener = prepared_telegraph
    config = replace(config, telegram=replace(config.telegram, original_text_messages=False),
                     secrets=replace(config.secrets, telegram_channel_id="@example_channel"))
    assert send.send_digest(config) == 0
    assert len(opener.messages) == 2 and opener.documents == 1
    documents = [payload for method, payload in opener.calls if method == "sendDocument"]
    assert all(payload["chat_id"] == config.secrets.telegram_chat_id for payload in documents)
    channel = opener.messages[1]
    assert "🔒" not in channel["text"] and "原文" not in channel["text"]


def test_dry_run_channel_and_site_backup_are_side_effect_free(prepared_photo, capsys, monkeypatch):
    from econ_digest.config import BackupConfig
    config, directory, opener = prepared_photo
    config = replace(config, telegram=replace(config.telegram, cover_photo=False, original_text_messages=False, send_report_file=False),
                     backup=BackupConfig(True, "https://example.invalid/private.git"),
                     secrets=replace(config.secrets, telegram_channel_id="@example_channel"))
    before = {p: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    monkeypatch.setattr("econ_digest.site.backup.subprocess.run", lambda *a, **kw: pytest.fail("dry run cannot run subprocess"))
    assert send.send_digest(config, dry_run=True) == 0
    text = capsys.readouterr().out
    private, channel = text.split("--- 頻道訊息 ---")
    assert "需帳密" in private and "需帳密" not in channel and "site.example" not in channel
    assert "將備份" in text and "--- 訊息 1/1 ---" in text and not opener.calls
    assert {p: p.read_bytes() for p in directory.iterdir() if p.is_file()} == before


def test_pages_only_rebuilds_site_publishes_and_backs_up_preserving_state(prepared_photo, monkeypatch):
    from econ_digest.config import BackupConfig
    config, directory, opener = prepared_photo
    config = replace(config, backup=BackupConfig(True, "https://example.invalid/private.git"))
    calls = []
    monkeypatch.setattr(send, "backup_output", lambda *args, **kw: calls.append((args, kw)))
    assert send.send_digest(config, pages_only=True) == 0
    assert (config.paths.output_dir / "2026-10-03/index.html").is_file()
    assert calls and calls[0][1]["record_state"] is False
    assert not (config.paths.data_dir / "state.json").exists()
    assert not (directory / "telegram_progress.json").exists()
    assert not opener.messages and not opener.photos and not opener.documents
