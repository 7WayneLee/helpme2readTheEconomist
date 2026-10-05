from __future__ import annotations

import argparse

from ..config import Config
from ..pipeline import run_pipeline
from . import add_issue_argument


def configure(parser: argparse.ArgumentParser) -> None:
    add_issue_argument(parser)
    parser.add_argument("--no-send", action="store_true", help="產生報告但不傳送")
    parser.add_argument("--dry-run", action="store_true", help="執行分析並產生報告但不傳送")
    parser.add_argument("--force", action="store_true", help="處理已傳送的期別並重新傳送")
    parser.add_argument("--reanalyze", action="store_true", help="重新執行分析")


def run(args: argparse.Namespace, config: Config) -> int:
    return run_pipeline(config, args.issue, no_send=args.no_send, dry_run=args.dry_run,
                        force=args.force, reanalyze=args.reanalyze)
