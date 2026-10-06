"""Atomic run history and a process-scoped, nonblocking Unix lock."""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TypedDict

from .models import Article, save_json


class AlreadyRunning(RuntimeError):
    """Another process owns the digest run lock."""


class StateError(ValueError):
    """Saved state is invalid; do not silently discard delivery history."""


class DeliveryRecord(TypedDict):
    delivered_at: str
    message_count: int


class EnglishHistoryRecord(TypedDict):
    issue_date: str
    article_id: str
    section: str
    kind: str
    title: str


class LastRunRecord(TypedDict):
    started_at: str | None
    finished_at: str | None
    issue_date: str | None
    outcome: str | None
    error: str | None


class State(TypedDict):
    delivered: dict[str, DeliveryRecord]
    english_history: list[EnglishHistoryRecord]
    last_run: LastRunRecord
    backup: dict[str, str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_state() -> State:
    return {
        "delivered": {}, "english_history": [], "backup": {},
        "last_run": {"started_at": None, "finished_at": None, "issue_date": None, "outcome": None, "error": None},
    }


def load_state(data_dir: str | Path) -> State:
    path = Path(data_dir) / "state.json"
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError:
        return empty_state()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateError("無法讀取 state.json；請先檢查狀態檔") from exc
    if not isinstance(data, dict):
        raise StateError("state.json 必須是 JSON 物件")
    state = empty_state()
    state.update(data)
    if not isinstance(state["delivered"], dict) or not isinstance(state["english_history"], list) or not isinstance(state["last_run"], dict):
        raise StateError("state.json 的 delivered、english_history 或 last_run 格式錯誤")
    return state


def save_state(data_dir: str | Path, state: State) -> None:
    save_json(Path(data_dir) / "state.json", state)


def record_english(state: State, issue_date: str, article: Article) -> None:
    """Keep the last delivered pick as the sole record for this issue."""
    record: EnglishHistoryRecord = {
        "issue_date": issue_date, "article_id": article.id, "section": article.section,
        "kind": article.kind, "title": article.title,
    }
    state["english_history"] = [item for item in state["english_history"]
                                if item.get("issue_date") != issue_date] + [record]


@contextmanager
def run_lock(data_dir: str | Path) -> Iterator[None]:
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunning("已有 econ-digest 程序正在執行") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class StateStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)

    def load(self) -> State:
        return load_state(self.data_dir)

    def save(self, state: State) -> None:
        save_state(self.data_dir, state)

    def is_delivered(self, issue_date: str) -> bool:
        return issue_date in self.load()["delivered"]

    def mark_delivered(self, issue_date: str, message_count: int) -> None:
        state = self.load()
        state["delivered"][issue_date] = {"delivered_at": utc_now(), "message_count": message_count}
        self.save(state)

    def record_english(self, issue_date: str, article: Article) -> None:
        state = self.load()
        record_english(state, issue_date, article)
        self.save(state)

    def start_run(self, issue_date: str | None = None) -> None:
        state = self.load()
        state["last_run"] = {
            "started_at": utc_now(), "finished_at": None, "issue_date": issue_date,
            "outcome": "running", "error": None,
        }
        self.save(state)

    def finish_run(self, outcome: str, error: str | None = None) -> None:
        state = self.load()
        state["last_run"].update(finished_at=utc_now(), outcome=outcome, error=error)
        self.save(state)
