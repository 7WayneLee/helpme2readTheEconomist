"""Stable issue/article keys and durable post/container progress under data/social."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from urllib.parse import urlsplit

from ..config import ThreadsConfig
from ..models import Digest, load_json, save_json
from ..render.common import sections
from ..render.telegraph import PREVIEW_URL, render_telegraph
from ..state import StateError, run_lock
from ..telegraph.publish import load_pages
from .formatting import Post, article_post, character_count, intro_post
from .tokens import timestamp

GROUPS = {"taiwan": "台灣", "focus": "本週焦點", "international": "國際", "topics": "財經・科技・文化"}


def _group(anchor: str) -> str:
    return "taiwan" if anchor.startswith("taiwan-") else "focus" if anchor == "focus" else (
        "international" if anchor.startswith("intl-") else "topics")


def _public_url(value: object, *, telegraph: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password
            or telegraph and parsed.hostname != "telegra.ph"):
        return None
    return value


def prepare_posts(directory: Path, config: ThreadsConfig, *, preview: bool = False,
                  page_limit_bytes: int = 60000) -> list[Post]:
    digest = load_json(directory / "digest.json", Digest)
    pages = {p.key: p.url for p in load_pages(directory / "telegraph_pages.json")}
    cover_url = None
    record = directory / "site_publish.json"
    if record.exists():
        cover_url = _public_url(json.loads(record.read_text(encoding="utf-8")).get("cover_url"))
    # Older deliveries keep the public cover in their resumable Telegram record.
    for name in ("telegram_progress.json",):
        path = directory / name
        if cover_url is None and path.exists():
            cover_url = _public_url(json.loads(path.read_text(encoding="utf-8")).get("cover_url"))
    if cover_url is None:
        # Support a locally saved Telegraph cover record without fetching pages.
        path = directory / "telegraph_cover.json"
        if path.exists():
            cover_url = _public_url(json.loads(path.read_text(encoding="utf-8")).get("cover_url"))
    if not preview and cover_url is None:
        raise ValueError("找不到已發布的公開封面網址；請先完成網站與 Telegraph 發布。")

    def page_url(key: str) -> str:
        url = _public_url(pages.get(key), telegraph=True)
        if url:
            return url
        if preview:
            return PREVIEW_URL
        raise ValueError("找不到所需的 Telegraph 頁面；請先完成本期發布。")

    # Preserve continuation-page destinations using the same local renderer.
    reserve = max([len(PREVIEW_URL), *[len(url.encode("utf-8")) for url in pages.values()]])
    rendered = render_telegraph(digest, page_limit_bytes, url_reserve_bytes=reserve, cover_url=cover_url)
    destinations: dict[str, str] = {}
    identifiers = {article.id: digest.classifications[article.id].title_zh
                   for article in digest.issue.articles if article.id in digest.classifications}
    def strings(nodes: list) -> set[str]:
        result: set[str] = set()
        for node in nodes:
            if isinstance(node, str):
                result.add(node)
            elif isinstance(node, dict):
                result.update(strings(node.get("children", [])))
        return result
    from ..render.common import clean_text
    for page in rendered:
        if page.key.split(":")[0] not in GROUPS:
            continue
        content = strings(page.nodes)
        for identifier, heading in identifiers.items():
            if clean_text(heading) in content:
                destinations.setdefault(identifier, page.key)
    result = [intro_post(digest, page_url("weekly:1"), cover_url, config)]
    seen = set()
    for section in sections(digest):
        group = _group(section.anchor)
        if GROUPS[group] not in config.sections:
            continue
        for entry in section.entries:
            identifier = entry.article.id
            if identifier in seen or entry.classification.tier == "merged":
                continue
            seen.add(identifier)
            key = "weekly:1" if config.link_target == "weekly" else destinations.get(identifier, f"{group}:1")
            result.append(article_post(digest, entry, GROUPS[group], page_url(key), config))
    return result


class Queue:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "social"
        self.path = self.directory / "threads_queue.json"

    def lock(self):
        return run_lock(self.directory)

    def load(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"version": 1, "posts": [], "paused": False, "alerts": {}, "failures": 0,
                    "next_attempt_at": None, "last_posted_at": None, "account_hash": None}
        except (OSError, ValueError) as exc:
            raise StateError("Threads 佇列無法讀取；請先檢查狀態檔，勿刪除發布紀錄。") from exc
        try:
            if (not isinstance(state, dict) or type(state["version"]) is not int or state["version"] != 1
                    or type(state["paused"]) is not bool or not isinstance(state["alerts"], dict)
                    or not isinstance(state["posts"], list)
                    or type(state["failures"]) is not int or state["failures"] < 0):
                raise ValueError
            for name in ("last_posted_at", "next_attempt_at"):
                if state.get(name):
                    timestamp(state[name])
            keys = set()
            for record in state["posts"]:
                post = Post(**record["post"])
                if (any(not isinstance(value, str) or not value for value in (
                    post.key, post.issue_date, post.article_id, post.section, post.text, post.link_url))
                        or post.key in keys or post.key != f"{post.issue_date}:{post.article_id}"
                        or record["status"] not in ("pending", "container", "publishing", "posted", "uncertain")
                        or character_count(post.text) > 500 or not _public_url(post.link_url, telegraph=True)
                        or post.image_url is not None and not _public_url(post.image_url)):
                    raise ValueError
                for name in ("container_id", "post_id"):
                    if record[name] is not None and (not isinstance(record[name], str) or not record[name]):
                        raise ValueError
                for name in ("created_at", "published_at", "publish_started_at"):
                    if record.get(name):
                        timestamp(record[name])
                if record["status"] == "posted" and (not record["post_id"] or not record["published_at"]):
                    raise ValueError
                if record["status"] in ("container", "publishing") and not record["container_id"]:
                    raise ValueError
                if record["status"] == "publishing" and not record.get("publish_started_at"):
                    raise ValueError
                keys.add(post.key)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise StateError("Threads 佇列格式錯誤；請保留原檔並檢查發布紀錄。") from exc
        return state

    def save(self, state: dict) -> None:
        save_json(self.path, state)

    def enqueue(self, posts: list[Post]) -> int:
        with self.lock():
            state = self.load()
            known = {record["post"]["key"] for record in state["posts"]}
            added = 0
            for post in posts:
                if post.key in known:
                    continue
                state["posts"].append({"post": asdict(post), "status": "pending", "container_id": None,
                                       "post_id": None, "created_at": None, "published_at": None})
                known.add(post.key)
                added += 1
            self.save(state)
            return added

    @staticmethod
    def next(state: dict) -> dict | None:
        return next((p for p in state["posts"] if p["status"] != "posted"), None)
