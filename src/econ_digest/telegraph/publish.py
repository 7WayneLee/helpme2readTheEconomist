"""Two-pass publication with stable per-issue paths and crash-safe allocation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import secrets

from ..config import TelegraphConfig
from ..models import save_json
from ..render.telegraph import Page, with_navigation
from .client import TelegraphClient
from .nodes import content_size, node, validate_nodes


@dataclass(frozen=True)
class PublishedPage:
    key: str
    path: str
    url: str


def load_pages(path: Path) -> list[PublishedPage]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("telegraph_pages.json 必須是頁面陣列")
    result = []
    for record in data:
        if (not isinstance(record, dict) or any(not isinstance(record.get(key), str) or not record[key]
                                               for key in ("key", "path", "url"))):
            raise ValueError("telegraph_pages.json 頁面紀錄無效")
        result.append(PublishedPage(record["key"], record["path"], record["url"]))
    if len({page.key for page in result}) != len(result) or len({page.path for page in result}) != len(result):
        raise ValueError("telegraph_pages.json 包含重複頁面")
    return result


def publish_pages(client: TelegraphClient, pages: list[Page], path: Path,
                  config: TelegraphConfig) -> list[PublishedPage]:
    # Validate all local trees before even allocating a public placeholder.
    for page in pages:
        validate_nodes(page.nodes)
        if content_size(page.nodes) > config.page_limit_bytes:
            raise ValueError("Telegraph 內容超過設定的頁面上限")
    stored = load_pages(path)
    by_key = {page.key: page for page in stored}
    author = {"author_name": config.author_name, "author_url": config.author_url}
    placeholder = [node("p", "導讀頁面準備中。")]
    for page in pages:
        if page.key not in by_key:
            created = client.create_page(secrets.token_hex(8), placeholder, **author)
            record = PublishedPage(page.key, created["path"], created["url"])
            stored.append(record)
            by_key[page.key] = record
            # Save each allocation immediately: retry after an edit failure reuses it.
            save_json(path, stored)
    urls = {page.key: by_key[page.key].url for page in pages}
    final_pages = with_navigation(pages, urls)
    for page in final_pages:
        if content_size(page.nodes) > config.page_limit_bytes:
            raise ValueError("Telegraph 內容與導覽超過設定的頁面上限")
    for page in final_pages:
        client.edit_page(by_key[page.key].path, page.title, page.nodes, **author)
    for old in stored:
        if old.key not in urls:
            client.edit_page(old.path, "此頁已不再使用", [node("p", "此頁已不再使用。"),
                             node("p", node("a", "閱讀本期導讀", href=urls[pages[0].key]))], **author)
    # Retain inactive records so later growth reuses these paths as well.
    save_json(path, stored)
    return [by_key[page.key] for page in pages]
