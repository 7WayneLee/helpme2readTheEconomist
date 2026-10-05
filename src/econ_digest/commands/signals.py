from __future__ import annotations

import argparse

from ..config import Config
from ..signals import find_taiwan_signals
from . import add_issue_argument, load_or_parse_issue


def configure(parser: argparse.ArgumentParser) -> None:
    add_issue_argument(parser)


def run(args: argparse.Namespace, config: Config) -> int:
    issue = load_or_parse_issue(config, args.issue)
    for article in issue.articles:
        signals = find_taiwan_signals(article)
        if signals.strong_terms:
            print(f"{article.title}\n  提及次數：{signals.mention_count}；詞彙：{', '.join(signals.strong_terms)}")
            if signals.snippets:
                print(f"  {signals.snippets[0]}")
    return 0
