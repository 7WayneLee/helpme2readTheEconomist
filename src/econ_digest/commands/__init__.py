"""Reusable issue selection and cache loading for pluggable commands."""

from __future__ import annotations

import argparse

from ..config import Config
from ..epub_parser import parse_epub
from ..fetch import Fetcher, issue_directory, issue_url
from ..models import Issue, load_json, save_json


def add_issue_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--issue", default="latest", metavar="latest|YYYY.MM.DD", help="期別（預設 latest；也接受 YYYY-MM-DD）")


def load_or_parse_issue(config: Config, issue_spec: str) -> Issue:
    fetcher = Fetcher(config)
    date = fetcher.resolve_issue(issue_spec)
    cache = issue_directory(config, date) / "issue.json"
    if cache.exists():
        return load_json(cache, Issue)
    epub = fetcher.download_issue(date)
    issue = parse_epub(epub, date, issue_url(date, config))
    save_json(cache, issue)
    return issue
