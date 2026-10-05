"""Discover and cache Economist issues using GitHub's public endpoints."""

from __future__ import annotations

import json
import http.client
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import Config, load_config

TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


class FetchError(RuntimeError):
    """A source listing or issue download could not be completed."""


def normalize_issue_date(spec: str) -> str:
    if not re.fullmatch(r"\d{4}(?:\.\d{2}\.\d{2}|-\d{2}-\d{2})", spec):
        raise FetchError("期別必須是 latest、YYYY.MM.DD 或 YYYY-MM-DD")
    normalized = spec.replace("-", ".")
    try:
        datetime.strptime(normalized, "%Y.%m.%d")
    except ValueError as exc:
        raise FetchError("期別日期無效") from exc
    return normalized


def issue_url(issue_date: str, config: Config) -> str:
    date = normalize_issue_date(issue_date)
    source = config.source
    repo = urllib.parse.quote(source.repo, safe="/")
    branch = urllib.parse.quote(source.branch, safe="")
    folder = urllib.parse.quote(source.folder.strip("/"), safe="/")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{folder}/te_{date}/TheEconomist.{date}.epub"


def issue_directory(config: Config, issue_date: str) -> Path:
    return config.paths.data_dir / "issues" / f"te_{normalize_issue_date(issue_date)}"


def _valid_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return archive.testzip() is None
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError):
        return False


class Fetcher:
    def __init__(
        self, config: Config | None = None, *, opener: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or load_config()
        self.opener = opener
        self.sleep = sleep

    def _open(self, request: urllib.request.Request) -> Any:
        opener = self.opener or urllib.request.urlopen
        if hasattr(opener, "open"):
            opener = opener.open
        return opener(request, timeout=TIMEOUT_SECONDS)

    def _request(self, url: str, *, authenticate: bool = False) -> urllib.request.Request:
        headers = {"User-Agent": "econ-digest"}
        if authenticate and self.config.secrets.github_token:
            headers["Authorization"] = f"Bearer {self.config.secrets.github_token}"
        return urllib.request.Request(url, headers=headers)

    def _retry(self, action: Callable[[], Any], description: str) -> Any:
        for attempt in range(MAX_RETRIES + 1):
            try:
                return action()
            except urllib.error.HTTPError as exc:
                if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == MAX_RETRIES:
                    raise FetchError(f"{description}：HTTP {exc.code}") from exc
            except (urllib.error.URLError, OSError, http.client.HTTPException, zipfile.BadZipFile, ValueError) as exc:
                if attempt == MAX_RETRIES:
                    raise FetchError(f"{description}：重試 {MAX_RETRIES} 次後仍失敗（{type(exc).__name__}）") from exc
            self.sleep(float(2 ** attempt))
        raise AssertionError("unreachable")

    def list_issue_dates(self) -> list[str]:
        source = self.config.source
        repo = urllib.parse.quote(source.repo, safe="/")
        folder = urllib.parse.quote(source.folder.strip("/"), safe="/")
        query = urllib.parse.urlencode({"ref": source.branch})
        url = f"https://api.github.com/repos/{repo}/contents/{folder}?{query}"

        def listing() -> list[str]:
            with self._open(self._request(url, authenticate=True)) as response:
                entries = json.load(response)
            if not isinstance(entries, list):
                raise ValueError("GitHub listing must be an array")
            dates: set[str] = set()
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("type") != "dir":
                    continue
                name = entry.get("name", "")
                if not isinstance(name, str) or not re.fullmatch(r"te_\d{4}\.\d{2}\.\d{2}", name):
                    continue
                try:
                    dates.add(normalize_issue_date(name[3:]))
                except FetchError:
                    continue
            return sorted(dates)

        return self._retry(listing, "無法取得 GitHub 期別清單")

    def latest_issue_date(self) -> str:
        dates = self.list_issue_dates()
        if not dates:
            raise FetchError("GitHub 來源目錄沒有有效的 Economist 期別")
        return dates[-1]

    def resolve_issue(self, spec: str) -> str:
        return self.latest_issue_date() if spec == "latest" else normalize_issue_date(spec)

    def download_issue(self, issue_date: str) -> Path:
        date = normalize_issue_date(issue_date)
        directory = issue_directory(self.config, date)
        path = directory / f"TheEconomist.{date}.epub"
        if _valid_zip(path):
            return path
        directory.mkdir(parents=True, exist_ok=True)

        def download() -> Path:
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=directory, prefix=".download-", delete=False) as stream:
                    temporary = Path(stream.name)
                    with self._open(self._request(issue_url(date, self.config))) as response:
                        while chunk := response.read(1024 * 1024):
                            stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                if not _valid_zip(temporary):
                    raise zipfile.BadZipFile("Downloaded file is not a valid ZIP archive")
                os.replace(temporary, path)
                return path
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

        return self._retry(download, f"無法下載 {date} 期 EPUB")


def latest_issue_date(config: Config | None = None) -> str:
    return Fetcher(config).latest_issue_date()


def resolve_issue(spec: str, config: Config | None = None) -> str:
    return Fetcher(config).resolve_issue(spec)


def download_issue(issue_date: str, config: Config | None = None) -> Path:
    return Fetcher(config).download_issue(issue_date)


def fetch_issue(config: Config, issue_spec: str = "latest") -> Path:
    fetcher = Fetcher(config)
    return fetcher.download_issue(fetcher.resolve_issue(issue_spec))
