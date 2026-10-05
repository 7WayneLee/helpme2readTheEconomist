from __future__ import annotations

import argparse

from ..config import Config
from ..fetch import issue_directory
from ..models import save_json
from . import add_issue_argument, load_or_parse_issue


def configure(parser: argparse.ArgumentParser) -> None:
    add_issue_argument(parser)


def run(args: argparse.Namespace, config: Config) -> int:
    issue = load_or_parse_issue(config, args.issue)
    save_json(issue_directory(config, issue.issue_date) / "issue.json", issue)
    sections: dict[str, tuple[int, int]] = {}
    for article in issue.articles:
        count, words = sections.get(article.section, (0, 0))
        sections[article.section] = (count + 1, words + article.word_count)
    print("章節\t文章數\t字數")
    for section, (count, words) in sections.items():
        print(f"{section}\t{count}\t{words}")
    print(f"合計\t{len(issue.articles)}\t{sum(article.word_count for article in issue.articles)}")
    return 0
