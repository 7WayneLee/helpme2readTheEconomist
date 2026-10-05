from __future__ import annotations

from dataclasses import replace
import io
import json
from pathlib import Path
import re
import traceback
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote
from urllib.request import OpenerDirector, Request

import pytest

from econ_digest.config import TelegraphConfig
from econ_digest.models import save_json
from econ_digest.render.telegraph import Page
from econ_digest.telegraph import TelegraphClient, TelegraphError, content_size, validate_nodes
from econ_digest.telegraph.nodes import node
from econ_digest.telegraph.publish import load_pages, publish_pages

TOKEN = "SYNTHETIC_TELEGRAPH_SECRET"


class Response(io.BytesIO):
    status = 200


class Opener(OpenerDirector):
    def __init__(self, events: list | None = None) -> None:
        super().__init__()
        self.events = events
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.fail_at: int | None = None

    def open(self, request: Request, timeout: float = 30) -> Response:
        assert request.get_method() == "POST"
        assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
        assert TOKEN not in request.full_url
        method = request.full_url.removeprefix("https://api.telegra.ph/")
        payload = {key: values[0] for key, values in parse_qs(request.data.decode(), keep_blank_values=True).items()}
        self.requests.append((method, payload))
        if len(self.requests) == self.fail_at:
            raise URLError(TOKEN)
        if self.events is not None:
            assert self.events, "unexpected API call"
            event = self.events.pop(0)
            if isinstance(event, Exception):
                raise event
            return Response(event if isinstance(event, bytes) else json.dumps(event).encode())
        if method == "createAccount":
            result = {"short_name": "econ-digest", "author_name": payload["author_name"], "access_token": TOKEN}
        else:
            assert payload["access_token"] == TOKEN
            validate_nodes(json.loads(payload["content"]))
            path = payload["title"] + "-10-05" if method == "createPage" else unquote(method.removeprefix("editPage/"))
            result = {"path": path, "url": "https://telegra.ph/" + path, "title": payload["title"]}
        return Response(json.dumps({"ok": True, "result": result}).encode())


def test_form_encoding_and_utf8_content() -> None:
    opener = Opener()
    client = TelegraphClient(TOKEN, opener=opener)
    content = [node("p", "台灣 & 中譯")]
    account = client.create_account(author_name="作者", author_url="")
    assert account["access_token"] == TOKEN
    page = client.create_page("測試頁", content, author_name="作者", author_url="https://example.invalid/a?b=c&d=e")
    assert client.edit_page(page["path"], "正式標題", content)["path"] == page["path"]
    assert opener.requests[1][1]["content"] == json.dumps(content, ensure_ascii=False)
    assert opener.requests[1][1]["return_content"] == "false"
    assert opener.requests[1][1]["author_url"].endswith("b=c&d=e")
    assert TOKEN not in repr(client)


def test_flood_wait_retries_five_times() -> None:
    sleeps = []
    opener = Opener([{"ok": False, "error": "FLOOD_WAIT_7"}] * 5 + [{"ok": True, "result": {"access_token": TOKEN}}])
    assert TelegraphClient(opener=opener, sleep=sleeps.append).create_account()["access_token"] == TOKEN
    assert sleeps == [7] * 5 and len(opener.requests) == 6


def test_flood_wait_exhaustion() -> None:
    sleeps = []
    opener = Opener([{"ok": False, "error": "FLOOD_WAIT_2"}] * 6)
    with pytest.raises(TelegraphError, match="FLOOD_WAIT_2"):
        TelegraphClient(opener=opener, sleep=sleeps.append).create_account()
    assert sleeps == [2] * 5


@pytest.mark.parametrize("event", [
    URLError(TOKEN), TimeoutError(TOKEN), b"invalid json " + TOKEN.encode(),
    {"ok": False, "error": "bad response " + TOKEN},
    {"ok": False, "error": TOKEN}, {"ok": True}, {"ok": True, "result": []},
    HTTPError("https://api.telegra.ph/test?access_token=" + TOKEN, 500, TOKEN, {}, io.BytesIO(TOKEN.encode())),
])
def test_errors_and_tracebacks_hide_tokens(event: object, caplog: pytest.LogCaptureFixture) -> None:
    client = TelegraphClient(TOKEN, opener=Opener([event]))
    with pytest.raises(TelegraphError) as info:
        client.create_page("測試", [node("p", "內容")])
    assert TOKEN not in str(info.value)
    assert TOKEN not in "".join(traceback.format_exception(info.value))
    assert info.value.__context__ is None
    assert TOKEN not in caplog.text


def test_api_error_code() -> None:
    with pytest.raises(TelegraphError, match="ACCESS_TOKEN_INVALID"):
        TelegraphClient(TOKEN, opener=Opener([{"ok": False, "error": "ACCESS_TOKEN_INVALID"}])).create_page("測試", [])


@pytest.mark.parametrize("content", [
    [{"tag": "details"}], [{"tag": "table"}], [{"tag": "p", "attrs": {"style": "color:red"}}],
    [{"tag": "p", "children": [{"tag": "script"}]}], [123], [{"tag": "p", "children": "oops"}],
    [{"tag": "p", "attrs": {"href": 4}}], [{"tag": []}], [{"tag": "p", "html": "x"}],
])
def test_invalid_nodes_rejected_before_request(content: list) -> None:
    opener = Opener()
    with pytest.raises(ValueError):
        TelegraphClient(TOKEN, opener=opener).create_page("測試", content)
    assert not opener.requests


@pytest.mark.parametrize("title", ["", "x" * 257])
def test_title_length(title: str) -> None:
    with pytest.raises(ValueError):
        TelegraphClient(TOKEN, opener=Opener()).create_page(title, [])


def test_content_size_counts_utf8_not_characters() -> None:
    content = [node("p", "台灣" * 12000)]
    assert content_size(content) > 64000
    with pytest.raises(ValueError, match="64000"):
        TelegraphClient(TOKEN, opener=Opener()).create_page("測試", content)


def pages() -> list[Page]:
    return [Page("weekly:1", 0, 1, "正式本週導讀", [node("p", "內容一")]),
            Page("english:1", 3, 1, "正式英文學習", [node("p", "內容二")])]


def test_random_allocate_then_edit_and_navigation(tmp_path: Path) -> None:
    opener = Opener()
    records = publish_pages(TelegraphClient(TOKEN, opener=opener), pages(), tmp_path / "pages.json", TelegraphConfig())
    assert [method.split("/")[0] for method, _ in opener.requests] == ["createPage", "createPage", "editPage", "editPage"]
    for (_, payload), record in zip(opener.requests[:2], records):
        assert re.fullmatch(r"[0-9a-f]{16}", payload["title"])
        assert record.path.startswith(payload["title"])
        assert "正式" not in payload["content"]
    for index, (_, payload) in enumerate(opener.requests[2:]):
        nodes = json.loads(payload["content"])
        assert nodes[0]["tag"] == "p" and nodes[-1]["tag"] == "p"
        assert nodes[0]["children"][index * 2]["tag"] == "b"
        assert records[1 - index].url in payload["content"]


def test_republish_grow_shrink_and_reuse_inactive_paths(tmp_path: Path) -> None:
    opener = Opener()
    client = TelegraphClient(TOKEN, opener=opener)
    path = tmp_path / "pages.json"
    original = publish_pages(client, pages(), path, TelegraphConfig())
    again = publish_pages(client, pages(), path, TelegraphConfig())
    assert original == again
    assert sum(method == "createPage" for method, _ in opener.requests) == 2
    extra = replace(pages()[0], key="weekly:2", part=2, title="正式本週導讀（續）")
    grown = publish_pages(client, [pages()[0], extra, pages()[1]], path, TelegraphConfig())
    assert sum(method == "createPage" for method, _ in opener.requests) == 3
    publish_pages(client, pages(), path, TelegraphConfig())
    assert opener.requests[-1][1]["title"] == "此頁已不再使用"
    assert "此頁已不再使用" in opener.requests[-1][1]["content"]
    regrown = publish_pages(client, [pages()[0], extra, pages()[1]], path, TelegraphConfig())
    assert grown == regrown
    assert sum(method == "createPage" for method, _ in opener.requests) == 3
    assert len(load_pages(path)) == 3


@pytest.mark.parametrize("failure", [2, 3, 4])
def test_resume_mid_publish_preserves_every_allocated_path(tmp_path: Path, failure: int) -> None:
    opener = Opener()
    opener.fail_at = failure
    client = TelegraphClient(TOKEN, opener=opener)
    path = tmp_path / "pages.json"
    with pytest.raises(TelegraphError):
        publish_pages(client, pages(), path, TelegraphConfig())
    allocated = load_pages(path)
    opener.fail_at = None
    published = publish_pages(client, pages(), path, TelegraphConfig())
    for record in allocated:
        assert record in published
    successful_creates = [payload["title"] for index, (method, payload) in enumerate(opener.requests, 1)
                          if method == "createPage" and index != failure]
    assert len(successful_creates) == 2


def test_publish_validation_happens_before_allocation(tmp_path: Path) -> None:
    opener = Opener()
    invalid = replace(pages()[1], nodes=[{"tag": "details"}])
    with pytest.raises(ValueError):
        publish_pages(TelegraphClient(TOKEN, opener=opener), [pages()[0], invalid], tmp_path / "pages.json", TelegraphConfig())
    assert not opener.requests


@pytest.mark.parametrize("data", [{}, [None], [{"key": "a", "path": "p", "url": 2}],
                                   [{"key": "a", "path": "p", "url": "u"}] * 2])
def test_corrupt_page_records_not_silently_recreated(tmp_path: Path, data: object) -> None:
    path = tmp_path / "pages.json"
    save_json(path, data)
    with pytest.raises(ValueError):
        load_pages(path)
