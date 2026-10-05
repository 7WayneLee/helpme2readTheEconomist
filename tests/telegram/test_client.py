from __future__ import annotations

from email import policy
from email.parser import BytesParser
import io
from http.client import IncompleteRead
import json
from pathlib import Path
import traceback
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import OpenerDirector, Request

import pytest

from econ_digest.telegram.client import TelegramClient, TelegramError, discover_private_chats


_TOKEN = "123456:synthetic-secret-abc"
_URL = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.sleeps.append(duration)
        self.now += duration


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status


Event = dict[str, Any] | Exception | bytes | tuple[int, dict[str, Any]]


class FakeOpener(OpenerDirector):
    def __init__(self, events: list[Event], timer: FakeTime | None = None) -> None:
        super().__init__()
        self.events = events.copy()
        self.requests: list[Request] = []
        self.timeouts: list[float] = []
        self.times: list[float] = []
        self.timer = timer

    def open(self, fullurl: Request, data: bytes | None = None, timeout: float = 30) -> FakeResponse:
        self.requests.append(fullurl)
        self.timeouts.append(timeout)
        if self.timer is not None:
            self.times.append(self.timer.clock())
        assert self.events, "Unexpected HTTP request"
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        status = 200
        if isinstance(event, tuple):
            status, event = event
        body = event if isinstance(event, bytes) else json.dumps(event).encode("utf-8")
        return FakeResponse(body, status)


def success(result: Any = None) -> dict[str, Any]:
    return {"ok": True, "result": {"message_id": 42} if result is None else result}


def api_error(status: int, description: str = "synthetic error", **parameters: Any) -> HTTPError:
    body = json.dumps(
        {"ok": False, "error_code": status, "description": description, "parameters": parameters}
    ).encode("utf-8")
    return HTTPError(_URL, status, description, {}, io.BytesIO(body))


def make_client(events: list[Event], *, min_interval: float = 0) -> tuple[TelegramClient, FakeOpener, FakeTime]:
    timer = FakeTime()
    opener = FakeOpener(events, timer)
    client = TelegramClient(_TOKEN, opener=opener, sleep=timer.sleep, clock=timer.clock, min_interval=min_interval)
    return client, opener, timer


def json_body(request: Request) -> dict[str, Any]:
    assert request.data is not None
    return json.loads(request.data)


def test_send_message_body() -> None:
    client, opener, _ = make_client([success()])
    assert client.send_message(123, "<b>台灣</b>", disable_notification=True) == 42
    request = opener.requests[0]
    assert request.full_url == _URL
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json_body(request) == {
        "chat_id": 123,
        "text": "<b>台灣</b>",
        "parse_mode": "HTML",
        "disable_notification": True,
        "link_preview_options": {"is_disabled": True},
    }
    assert opener.timeouts == [30]


def test_get_me_and_updates() -> None:
    client, opener, timer = make_client([success({"id": 7, "is_bot": True}), success([]), success([])])
    assert client.get_me() == {"id": 7, "is_bot": True}
    assert client.get_updates(offset=100, timeout=20) == []
    assert client.get_updates() == []
    assert opener.requests[0].full_url.endswith("/getMe")
    assert json_body(opener.requests[0]) == {}
    assert json_body(opener.requests[1]) == {"offset": 100, "timeout": 20}
    assert json_body(opener.requests[2]) == {"timeout": 0}
    assert timer.sleeps == []


@pytest.mark.parametrize("filename", [None, "週報.html", 'report "synthetic".html'])
def test_send_document_multipart(tmp_path: Path, filename: str | None) -> None:
    document = tmp_path / "report.html"
    contents = "<html><body>台灣測試📌</body></html>".encode("utf-8")
    document.write_bytes(contents)
    client, opener, _ = make_client([success()])
    assert client.send_document("123", document, caption_html="<b>本週週報</b>", filename=filename) == 42
    request = opener.requests[0]
    assert request.full_url.endswith("/sendDocument")
    header = request.get_header("Content-type")
    assert header is not None
    assert request.data is not None
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {header}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii") + request.data
    )
    assert message.is_multipart()
    parts = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
    assert set(parts) == {"chat_id", "caption", "parse_mode", "document"}
    assert parts["chat_id"].get_payload(decode=True) == b"123"
    assert parts["caption"].get_payload(decode=True).decode("utf-8") == "<b>本週週報</b>"
    assert parts["parse_mode"].get_payload(decode=True) == b"HTML"
    assert parts["document"].get_filename() == (filename or "report.html")
    assert parts["document"].get_content_type() == "text/html"
    assert parts["document"].get_payload(decode=True) == contents


def test_send_document_without_caption_and_unknown_mime(tmp_path: Path) -> None:
    document = tmp_path / "fixture.unknown-synthetic-extension"
    document.write_bytes(b"synthetic\x00\xff")
    client, opener, _ = make_client([success()])
    client.send_document(4, document)
    body = opener.requests[0].data
    assert body is not None
    assert b"Content-Type: application/octet-stream" in body
    assert b'name="caption"' not in body
    assert b"synthetic\x00\xff" in body


def multipart_parts(request: Request) -> dict:
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {request.get_header('Content-type')}\r\nMIME-Version: 1.0\r\n\r\n".encode() + request.data)
    return {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}


def test_send_photo_multipart(synthetic_pngs: dict[str, bytes]) -> None:
    client, opener, _ = make_client([success()])
    assert client.send_photo(123, synthetic_pngs["cover"], caption_html="<b>本週封面</b>") == 42
    request = opener.requests[0]
    assert request.full_url.endswith("/sendPhoto")
    parts = multipart_parts(request)
    assert set(parts) == {"chat_id", "caption", "parse_mode", "photo"}
    assert parts["photo"].get_filename() == "cover.jpg"
    assert parts["photo"].get_content_type() == "image/jpeg"
    assert parts["photo"].get_payload(decode=True) == synthetic_pngs["cover"]
    assert parts["caption"].get_payload(decode=True).decode() == "<b>本週封面</b>"
    assert parts["chat_id"].get_payload(decode=True) == b"123"


def test_send_photo_no_caption(synthetic_pngs: dict[str, bytes]) -> None:
    client, opener, _ = make_client([success()])
    client.send_photo(1, synthetic_pngs["cover"], filename="cover.png")
    parts = multipart_parts(opener.requests[0])
    assert set(parts) == {"chat_id", "photo"}
    assert parts["photo"].get_content_type() == "image/png"


@pytest.mark.parametrize("filename", ["", "bad\r\n.png", "bad\x00.jpg"])
def test_photo_rejects_invalid_filename(filename: str) -> None:
    client, opener, _ = make_client([])
    with pytest.raises(ValueError):
        client.send_photo(1, b"synthetic", filename=filename)
    assert not opener.requests


def test_photo_plain_caption_fallback_once(synthetic_pngs: dict[str, bytes], caplog: pytest.LogCaptureFixture) -> None:
    client, opener, timer = make_client([api_error(400, "can't parse entities " + _TOKEN), success()], min_interval=1.1)
    client.send_photo_safe(7, synthetic_pngs["cover"], caption_html="<b>台灣 &amp; 😀</b>")
    first, plain = map(multipart_parts, opener.requests)
    assert first["parse_mode"].get_payload(decode=True) == b"HTML"
    assert "parse_mode" not in plain
    assert plain["caption"].get_payload(decode=True).decode() == "台灣 & 😀"
    assert plain["photo"].get_payload(decode=True) == synthetic_pngs["cover"]
    assert timer.sleeps == [1.1] and _TOKEN not in caplog.text


@pytest.mark.parametrize("status,description,attempts", [(400, "can't parse entities", 2), (400, "chat not found", 1),
                                                       (403, "can't parse entities", 1)])
def test_safe_photo_fallback_error_propagates(status: int, description: str, attempts: int) -> None:
    client, opener, _ = make_client([api_error(status, description) for _ in range(attempts)])
    with pytest.raises(TelegramError):
        client.send_photo_safe(1, b"synthetic", caption_html="<b>測試</b>")
    assert len(opener.requests) == attempts


def test_photo_retries_and_redaction() -> None:
    description = "Failure " + _URL
    client, opener, timer = make_client([api_error(429, retry_after=2), api_error(502), success()])
    client.send_photo_safe(1, b"synthetic")
    assert timer.sleeps == [2.5, 2] and len(opener.requests) == 3
    client, _, _ = make_client([api_error(400, description)])
    with pytest.raises(TelegramError) as caught:
        client.send_photo_safe(1, b"synthetic")
    assert _TOKEN not in "".join(traceback.format_exception(caught.value))


def test_photo_paces_between_message_and_document(tmp_path: Path) -> None:
    document = tmp_path / "report.html"
    document.write_text("合成報告")
    client, opener, timer = make_client([success()] * 3, min_interval=1.1)
    client.send_message(1, "第一則")
    client.send_photo(1, b"synthetic")
    client.send_document(1, document)
    assert opener.times == pytest.approx([0, 1.1, 2.2]) and timer.sleeps == [1.1, 1.1]


@pytest.mark.parametrize("filename", ["bad\r\nInjected: value.html", "bad\x00.html", ""])
def test_send_document_rejects_invalid_filename(tmp_path: Path, filename: str) -> None:
    client, opener, _ = make_client([])
    with pytest.raises(ValueError):
        client.send_document(1, tmp_path / "unused", filename=filename)
    assert not opener.requests


def test_429_retry_after() -> None:
    client, opener, timer = make_client([api_error(429, retry_after=3), success()])
    assert client.send_message(123, "test") == 42
    assert timer.sleeps == [3.5]
    assert len(opener.requests) == 2


def test_429_max_five_retries() -> None:
    client, opener, timer = make_client([api_error(429, retry_after=2) for _ in range(6)])
    with pytest.raises(TelegramError) as caught:
        client.send_message(1, "test")
    assert caught.value.status == 429
    assert timer.sleeps == [2.5] * 5
    assert len(opener.requests) == 6


@pytest.mark.parametrize("retry_after", [None, "invalid", -1, float("inf")])
def test_invalid_retry_after_uses_default(retry_after: Any) -> None:
    client, _, timer = make_client([api_error(429, retry_after=retry_after), success()])
    client.send_message(1, "test")
    assert timer.sleeps == [1.5]


def test_5xx_backoff_then_success() -> None:
    client, opener, timer = make_client([api_error(500), api_error(502), api_error(503), api_error(504), success()])
    assert client.send_message(1, "test") == 42
    assert timer.sleeps == [2, 4, 8, 16]
    assert len(opener.requests) == 5


def test_5xx_without_json_retries() -> None:
    client, _, timer = make_client([HTTPError(_URL, 502, "bad gateway", {}, io.BytesIO(b"not json")), success()])
    client.send_message(1, "test")
    assert timer.sleeps == [2]


@pytest.mark.parametrize("error_kind", [URLError, TimeoutError, ConnectionResetError])
def test_network_errors_retry(error_kind: type[Exception]) -> None:
    client, _, timer = make_client([error_kind("synthetic network failure"), success()])
    assert client.send_message(1, "test") == 42
    assert timer.sleeps == [2]


def test_response_read_timeout_retries_and_redacts(caplog: pytest.LogCaptureFixture) -> None:
    class ReadTimeoutResponse(FakeResponse):
        def read(self, size: int = -1) -> bytes:
            raise TimeoutError(_URL)

    class ReadTimeoutOpener(FakeOpener):
        def open(self, fullurl: Request, data: bytes | None = None, timeout: float = 30) -> FakeResponse:
            self.requests.append(fullurl)
            return ReadTimeoutResponse(b"")

    timer = FakeTime()
    opener = ReadTimeoutOpener([])
    client = TelegramClient(_TOKEN, opener=opener, sleep=timer.sleep, clock=timer.clock, min_interval=0)
    with pytest.raises(TelegramError) as caught:
        client.send_message(1, "test")
    assert len(opener.requests) == 5
    assert timer.sleeps == [2, 4, 8, 16]
    assert _TOKEN not in str(caught.value)
    assert _TOKEN not in "".join(traceback.format_exception(caught.value))
    assert _TOKEN not in caplog.text


def test_incomplete_http_response_retries() -> None:
    client, _, timer = make_client([IncompleteRead(b"synthetic", 42), success()])
    assert client.send_message(1, "test") == 42
    assert timer.sleeps == [2]


@pytest.mark.parametrize("error_type", [ValueError, UnicodeError])
def test_invalid_request_errors_are_sanitized(error_type: type[Exception], caplog: pytest.LogCaptureFixture) -> None:
    client, opener, timer = make_client([error_type(_URL)])
    with pytest.raises(TelegramError) as caught:
        client.send_message(1, "test")
    assert len(opener.requests) == 1
    assert timer.sleeps == []
    assert _TOKEN not in str(caught.value)
    assert _TOKEN not in "".join(traceback.format_exception(caught.value))
    assert _TOKEN not in caplog.text


def test_http_status_controls_retry_even_if_body_code_disagrees() -> None:
    client, _, timer = make_client([
        (429, {"ok": False, "error_code": 400, "description": "rate limit", "parameters": {"retry_after": 2}}),
        success(),
    ])
    assert client.send_message(1, "test") == 42
    assert timer.sleeps == [2.5]


def test_api_error_inside_success_http_response() -> None:
    client, _, timer = make_client([
        {"ok": False, "error_code": 429, "description": "slow down", "parameters": {"retry_after": 4}},
        success(),
    ])
    assert client.send_message(1, "test") == 42
    assert timer.sleeps == [4.5]


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_other_4xx_do_not_retry(status: int) -> None:
    client, opener, timer = make_client([api_error(status)])
    with pytest.raises(TelegramError) as caught:
        client.send_message(1, "test")
    assert caught.value.status == status
    assert timer.sleeps == []
    assert len(opener.requests) == 1


def test_safe_message_plain_text_fallback(caplog: pytest.LogCaptureFixture) -> None:
    client, opener, _ = make_client([api_error(400, "Bad Request: can't parse entities"), success()])
    assert client.send_message_safe(7, "<b>台灣 &amp; 晶片</b>\n<blockquote expandable>測試</blockquote>", disable_notification=True) == 42
    body = json_body(opener.requests[1])
    assert body == {
        "chat_id": 7,
        "text": "台灣 & 晶片\n測試",
        "disable_notification": True,
        "link_preview_options": {"is_disabled": True},
    }
    assert "plain text" in caplog.text


def test_safe_message_fallback_accepts_malformed_input() -> None:
    client, opener, _ = make_client([api_error(400, "can't parse entities"), success()])
    client.send_message_safe(1, "<b>未關閉 &amp; 標籤")
    assert json_body(opener.requests[1])["text"] == "未關閉 & 標籤"


def test_safe_message_fallback_only_once() -> None:
    client, opener, _ = make_client([api_error(400, "can't parse entities"), api_error(400, "can't parse entities")])
    with pytest.raises(TelegramError):
        client.send_message_safe(1, "<b>text</b>")
    assert len(opener.requests) == 2


@pytest.mark.parametrize("status,description", [(400, "chat not found"), (403, "can't parse entities")])
def test_safe_message_other_errors_propagate(status: int, description: str) -> None:
    client, opener, _ = make_client([api_error(status, description)])
    with pytest.raises(TelegramError):
        client.send_message_safe(1, "text")
    assert len(opener.requests) == 1


def test_pacing_across_send_methods(tmp_path: Path) -> None:
    document = tmp_path / "report.html"
    document.write_text("synthetic", encoding="utf-8")
    client, opener, timer = make_client([success(), success(), success(), success()], min_interval=1.1)
    client.send_message(1, "first")
    client.send_document(1, document)
    timer.now += 0.3
    client.send_message(1, "third")
    timer.now += 5
    client.send_message(1, "fourth")
    assert timer.sleeps == pytest.approx([1.1, 0.8])
    assert opener.times == pytest.approx([0, 1.1, 2.2, 7.2])


def test_pacing_also_applies_to_fallback_and_retries() -> None:
    client, opener, timer = make_client([api_error(429, retry_after=0), api_error(400, "can't parse entities"), success()], min_interval=1.1)
    client.send_message_safe(1, "<b>字</b>")
    assert opener.times == pytest.approx([0, 1.1, 2.2])
    assert timer.sleeps == pytest.approx([0.5, 0.6, 1.1])


@pytest.mark.parametrize("kind", ["http400", "http401", "http429", "http500", "url", "timeout", "reset", "raw_http", "json_error"])
def test_token_redacted_in_every_error_path(kind: str, caplog: pytest.LogCaptureFixture) -> None:
    description = f"Failed at {_URL} with token {_TOKEN}"
    if kind.startswith("http"):
        status = int(kind[4:])
        attempts = 6 if status == 429 else 5 if status >= 500 else 1
        events: list[Event] = [api_error(status, description, retry_after=0) for _ in range(attempts)]
    elif kind == "raw_http":
        events = [HTTPError(_URL, 403, description, {}, io.BytesIO(b"bad json"))]
    elif kind == "json_error":
        events = [{"ok": False, "error_code": 400, "description": description}]
    else:
        error_type = {"url": URLError, "timeout": TimeoutError, "reset": ConnectionResetError}[kind]
        events = [error_type(description) for _ in range(5)]
    client, _, _ = make_client(events)
    with pytest.raises(TelegramError) as caught:
        client.send_message(1, "test")
    error = caught.value
    assert _TOKEN not in str(error)
    assert _TOKEN not in repr(error)
    assert _TOKEN not in repr(client)
    assert _TOKEN not in caplog.text
    assert _TOKEN not in "".join(traceback.format_exception(error))
    assert error.__context__ is None
    assert "bot<redacted>" in str(error)


def test_fallback_log_does_not_leak_description(caplog: pytest.LogCaptureFixture) -> None:
    client, _, _ = make_client([api_error(400, f"can't parse entities at {_URL}"), success()])
    client.send_message_safe(1, "<b>字</b>")
    assert _TOKEN not in caplog.text
    assert "plain text" in caplog.text


def test_missing_document_filename_with_token_is_redacted(tmp_path: Path) -> None:
    client, _, _ = make_client([])
    with pytest.raises(TelegramError) as caught:
        client.send_document(1, tmp_path / _TOKEN)
    assert _TOKEN not in str(caught.value)
    assert _TOKEN not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("result", [[], {"message_id": "not an integer"}, {"message_id": True}, {}])
def test_invalid_message_result(result: Any) -> None:
    client, _, _ = make_client([success(result)])
    with pytest.raises(TelegramError):
        client.send_message(1, "test")


@pytest.mark.parametrize("response", [b"not json", [], {"ok": True}, {"ok": False}])
def test_malformed_api_response(response: Any) -> None:
    client, _, timer = make_client([response])
    with pytest.raises(TelegramError):
        client.send_message(1, "test")
    assert timer.sleeps == []


def test_discover_private_chats_newest_first() -> None:
    updates = [
        {"update_id": 3, "message": {"chat": {"id": 1, "type": "private", "username": "old", "first_name": "舊"}}},
        {"update_id": 5, "message": {"chat": {"id": 2, "type": "private", "first_name": "測試"}}},
        {"update_id": 6, "edited_message": {"chat": {"id": 1, "type": "private", "username": "new", "first_name": "新"}}},
        {"update_id": 7, "message": {"chat": {"id": -3, "type": "group"}}},
        {"update_id": 9, "callback_query": {"from": {"id": 4}}},
        {"update_id": 10, "message": {}},
        {"update_id": 11, "message": {"chat": {"type": "private"}}},
    ]
    client, _, _ = make_client([success(updates)])
    assert discover_private_chats(client) == [
        {"chat_id": 1, "username": "new", "first_name": "新"},
        {"chat_id": 2, "username": None, "first_name": "測試"},
    ]


def test_instant_view_link_preview_url() -> None:
    client, opener, _ = make_client([success()])
    client.send_message(123, '<a href="https://telegra.ph/test">導讀</a>', link_preview_url="https://telegra.ph/test")
    assert json_body(opener.requests[0])["link_preview_options"] == {"url": "https://telegra.ph/test", "prefer_large_media": False}


def test_link_preview_survives_plain_text_fallback() -> None:
    client, opener, _ = make_client([api_error(400, "can't parse entities"), success()])
    client.send_message_safe(123, '<a href="https://telegra.ph/test">導讀</a>', link_preview_url="https://telegra.ph/test")
    assert json_body(opener.requests[1])["link_preview_options"] == {"url": "https://telegra.ph/test", "prefer_large_media": False}
    assert "parse_mode" not in json_body(opener.requests[1])


def test_prefer_large_media_and_plain_text_retry_keep_preview():
    client, opener, _ = make_client([api_error(400, "can't parse entities"), success()])
    url = "https://telegra.ph/example"
    assert client.send_message_safe("@example_channel", "<b>摘要</b>", link_preview_url=url, prefer_large_media=True) == 42
    assert all(json_body(request)["link_preview_options"] == {"url": url, "prefer_large_media": True} for request in opener.requests)


def test_channel_api_methods():
    client, opener, _ = make_client([success({"id": -100123456789, "type": "channel"}), success({"status": "administrator", "can_post_messages": True})])
    assert client.get_chat("@example_channel")["type"] == "channel"
    assert client.get_chat_member(-100123456789, 7)["can_post_messages"]
    assert opener.requests[0].full_url.endswith("/getChat")
    assert json_body(opener.requests[0]) == {"chat_id": "@example_channel"}
    assert json_body(opener.requests[1]) == {"chat_id": -100123456789, "user_id": 7}
