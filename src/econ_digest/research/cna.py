"""Polite CNA search and short article excerpts; all caches stay under data/."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from ..models import Source, save_json

BASE_URL = "https://www.cna.com.tw"
USER_AGENT = "econ-digest/0.1 (Taiwan news evidence; limited requests)"
MAX_RESPONSE_BYTES = 2_000_000
REQUEST_INTERVAL = 2.5
SEARCH_TTL = 7 * 86400
ARTICLE_TTL = 30 * 86400
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Evidence:
    id: str
    source: Source
    excerpt: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, **self.source.to_dict(), "excerpt": self.excerpt}


def cna_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = urljoin(BASE_URL, value)
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "www.cna.com.tw"
            or not re.fullmatch(r"/news/[a-z]+/\d{12,}\.aspx", parsed.path)):
        return None
    return BASE_URL + parsed.path


def url_date(url: str) -> date | None:
    match = re.search(r"/news/[a-z]+/(\d{8})\d+\.aspx$", urlsplit(url).path)
    try:
        return date.fromisoformat(f"{match[1][:4]}-{match[1][4:6]}-{match[1][6:8]}") if match else None
    except ValueError:
        return None


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self._script: list[str] | None = None
        self._stack: list[tuple[str, bool]] = []
        self._paragraph: list[str] | None = None
        self.paragraphs: list[str] = []
        self._heading: list[str] | None = None
        self.headline = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and "ld+json" in (values.get("type") or "").lower():
            self._script = []
        if tag == "meta" and values.get("property") == "og:title" and not self.headline:
            self.headline = values.get("content") or ""
        if tag == "h1":
            self._heading = []
        body = any(active for _, active in self._stack)
        classes = (values.get("class") or "").split()
        body = body or "paragraph" in classes or values.get("itemprop") == "articleBody"
        if tag == "p" and body:
            self._paragraph = []
        if tag not in {"meta", "img", "br", "hr", "link", "input", "source", "wbr"}:
            self._stack.append((tag, body))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script is not None:
            self.scripts.append("".join(self._script))
            self._script = None
        if tag == "p" and self._paragraph is not None:
            value = " ".join("".join(self._paragraph).split())
            if value:
                self.paragraphs.append(value)
            self._paragraph = None
        if tag == "h1" and self._heading is not None:
            self.headline = " ".join("".join(self._heading).split())
            self._heading = None
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script.append(data)
        if self._heading is not None:
            self._heading.append(data)
        if self._paragraph is not None:
            self._paragraph.append(data)


def _objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def parse_search(html: str, *, today: date | None = None, limit: int = 5) -> list[Source]:
    parser = _Page()
    parser.feed(html)
    found: dict[str, Source] = {}
    today = today or date.today()
    for script in parser.scripts:
        try:
            data = json.loads(script)
        except ValueError:
            continue
        for obj in _objects(data):
            kind = obj.get("@type")
            if kind != "ItemList" and not (isinstance(kind, list) and "ItemList" in kind):
                continue
            elements = obj.get("itemListElement", [])
            if not isinstance(elements, list):
                continue
            for element in elements:
                if not isinstance(element, dict):
                    continue
                item = element.get("item", element)
                if not isinstance(item, dict):
                    continue
                url = cna_url(item.get("url") or item.get("@id"))
                published = url_date(url) if url else None
                name = item.get("name")
                if url and published and published <= today and isinstance(name, str) and name.strip():
                    found.setdefault(url, Source("中央社", published.isoformat(), name.strip()[:200], url))
    cutoff = today - timedelta(days=365)
    recent = [source for source in found.values() if date.fromisoformat(source.date) >= cutoff]
    candidates = recent or list(found.values())
    return sorted(candidates, key=lambda source: source.date, reverse=True)[:limit]


def parse_article(html: str) -> tuple[str, str]:
    parser = _Page()
    parser.feed(html)
    return parser.headline[:200], "\n".join(parser.paragraphs[:2])[:200]


class CNAClient:
    def __init__(self, cache_dir: Path, *, opener: Callable[..., Any] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time,
                 today: date | None = None, timeout: float = 15,
                 request_budget: int = 40, max_retries: int = 3) -> None:
        if type(request_budget) is not int or request_budget < 0:
            raise ValueError("request_budget must be a nonnegative integer")
        if type(max_retries) is not int or not 0 <= max_retries <= 3:
            raise ValueError("max_retries must be 0–3")
        self.cache_dir = Path(cache_dir)
        self.opener = opener or urlopen
        self.sleep, self.clock, self.wall_clock = sleep, clock, wall_clock
        self.today, self.timeout = today or date.today(), timeout
        self._last_request: float | None = None
        self.request_budget, self.max_retries = request_budget, max_retries
        self.request_count = 0
        self.fetcher = None  # Attached only by the multi-source analysis client.
        self.robots_blocked = False
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def _retry_after(self, error: HTTPError) -> float:
        value = error.headers.get("Retry-After", "") if error.headers else ""
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = parsedate_to_datetime(value).timestamp() - self.wall_clock()
            except (ValueError, TypeError, OverflowError):
                return 0.0
        return max(0.0, seconds) if math.isfinite(seconds) else 0.0

    def _fetch(self, url: str) -> str | None:
        if self.fetcher is not None:
            before = len(self.fetcher.errors)
            result = self.fetcher.fetch(url)
            self.request_count = self.fetcher.request_count
            self.errors.extend(error for _, error in self.fetcher.errors[before:])
            return result
        retry_delay = 0.0
        for attempt in range(self.max_retries + 1):
            if self.request_count >= self.request_budget:
                if "request_budget" not in self.errors:
                    notice = f"中央社每次分析請求上限（{self.request_budget} 次）已達；後續查證僅使用快取。"
                    self.errors.append("request_budget")
                    self.warnings.append(notice)
                    logger.warning("%s", notice)
                return None
            spacing = (max(0.0, REQUEST_INTERVAL - (self.clock() - self._last_request))
                       if self._last_request is not None else 0.0)
            delay = max(spacing, retry_delay)
            if delay:
                self.sleep(delay)
            self._last_request = self.clock()
            self.request_count += 1
            request = Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise ValueError("CNA response too large")
                    final_url = getattr(response, "geturl", lambda: url)()
                    if urlsplit(final_url).netloc != "www.cna.com.tw":
                        raise ValueError("unexpected CNA redirect")
                return raw.decode("utf-8", errors="replace")
            except HTTPError as exc:
                if exc.code in {429, 503} and attempt < self.max_retries:
                    retry_delay = max(REQUEST_INTERVAL * 2 ** attempt, self._retry_after(exc))
                    exc.close()
                    continue
                self.errors.append(f"HTTPError:{exc.code}")
                exc.close()
                return None
            except (OSError, ValueError, TimeoutError) as exc:
                self.errors.append(type(exc).__name__)
                return None
        return None

    def _cached(self, url: str, ttl: float, parse: Callable[[str], Any]) -> Any:
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and cached.get("url") == url and 0 <= self.wall_clock() - cached["time"] < ttl:
                return cached["data"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        html = self._fetch(url)
        if html is None:
            return []
        try:
            data = parse(html)
        except (OSError, ValueError, TimeoutError) as exc:
            self.errors.append(type(exc).__name__)
            return []
        save_json(path, {"url": url, "time": self.wall_clock(), "data": data})
        # Bound the small parsed-data cache, never storing full article HTML.
        paths = sorted(self.cache_dir.glob("*.json"), key=lambda item: item.stat().st_mtime)
        for stale in paths[:-500]:
            stale.unlink(missing_ok=True)
        return data

    def search(self, query: str) -> list[Source]:
        url = BASE_URL + "/search/hysearchws.aspx?" + urlencode({"q": query})
        if self.fetcher is not None and not self.fetcher.search_allowed(url):
            self.robots_blocked = True
            return []
        data = self._cached(url, SEARCH_TTL, lambda html: [source.to_dict() for source in parse_search(html, today=self.today)])
        # Recency is rechecked on cache reads, with dates derived from URLs again.
        sources = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("title"), str):
                continue
            url = cna_url(item.get("url"))
            published = url_date(url) if url else None
            if published and published <= self.today:
                sources.append(Source("中央社", published.isoformat(), item["title"], url))
        recent = [source for source in sources if url_date(source.url) >= self.today - timedelta(days=365)]
        return (recent or sources)[:5]

    def retrieve(self, queries: list[str]) -> list[Evidence]:
        found = self.retrieve_search(queries)
        result = []
        for entry in found:
            source = entry.source
            data = self._cached(source.url, ARTICLE_TTL, lambda html: list(parse_article(html)))
            if not data or len(data) != 2 or not data[1]:
                continue
            result.append(Evidence(f"cna{len(result) + 1}", Source(source.outlet, source.date,
                                   data[0] or source.title, source.url), data[1]))
        return result

    def retrieve_search(self, queries: list[str]) -> list[Evidence]:
        """Return dated search headlines only, without fetching article pages."""
        found: dict[str, Source] = {}
        for query in queries:
            for source in self.search(query):
                found.setdefault(source.url, source)
        return [Evidence(f"cna{index}", source, source.title)
                for index, source in enumerate(found.values(), 1)]
