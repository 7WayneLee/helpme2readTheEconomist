from __future__ import annotations

import argparse

from ..config import Config
from ..fetch import fetch_issue
from . import add_issue_argument


def configure(parser: argparse.ArgumentParser) -> None:
    add_issue_argument(parser)


def run(args: argparse.Namespace, config: Config) -> int:
    print(fetch_issue(config, args.issue))
    return 0
