"""Inspect analysis batches or produce a cached digest."""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from ..analysis.pipeline import AnalysisError, analyze_issue, analyze_selected, make_llm_client
from ..analysis.planning import plan_issue
from ..analysis.cache import read_cache
from ..config import Config
from ..fetch import issue_directory
from ..state import load_state, run_lock
from ..taxonomy import TIER_ORDER
from . import add_issue_argument, load_or_parse_issue


def _positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必須大於零")
    return number


def configure(parser: argparse.ArgumentParser) -> None:
    add_issue_argument(parser)
    parser.add_argument("--reanalyze", action="store_true", help="清除本期分析快取後重新分析")
    parser.add_argument("--plan", action="store_true", help="列出批次，不呼叫模型")
    parser.add_argument("--only-tier", choices=TIER_ORDER, help="僅產生指定深度的摘要")
    parser.add_argument("--limit", type=_positive, metavar="N", help="最多產生 N 篇摘要")


def run(args: argparse.Namespace, config: Config) -> int:
    with run_lock(config.paths.data_dir):
        issue = load_or_parse_issue(config, args.issue)
        workdir = issue_directory(config, issue.issue_date) / "analysis"
        history = load_state(config.paths.data_dir)["english_history"]
        if args.plan:
            units, estimated = plan_issue(issue, config, workdir=workdir, english_history=history,
                                           only_tier=args.only_tier, limit=args.limit)
            print(f"期別：{issue.issue_date}" + ("（尚無完整決策快取，摘要與英文指南批次為估計）" if estimated else ""))
            for unit in units:
                print(f"{unit.stage}: articles={len(unit.article_ids)} prompt_bytes={unit.prompt_bytes} models={','.join(unit.models)}")
            pending = sum(args.reanalyze or read_cache(workdir, unit) is None for unit in units)
            print(f"總計 {len(units)} 個呼叫單元；待呼叫 {pending}；最大提示詞 {max((unit.prompt_bytes for unit in units), default=0)} bytes")
            return 0
        if args.reanalyze and workdir.exists():
            for path in workdir.glob("*.json"):
                path.unlink()
        try:
            options = {"workdir": workdir, "english_history": history, "progress": print}
            if args.only_tier is not None or args.limit is not None:
                digest = analyze_selected(issue, config, make_llm_client(config), **options,
                                          only_tier=args.only_tier, limit=args.limit)
            else:
                digest = analyze_issue(issue, config, make_llm_client(config), **options)
        except AnalysisError as exc:
            print(f"錯誤：{exc}", file=sys.stderr)
            return 1
        tiers = Counter(item.tier for item in digest.classifications.values())
        levels = Counter(item.taiwan_level for item in digest.classifications.values())
        print("摘要深度：" + "、".join(f"{tier}={count}" for tier, count in sorted(tiers.items())))
        print("台灣關聯：" + "、".join(f"{level}={levels[level]}" for level in range(4)))
        selected = next((article.title for article in issue.articles if digest.english and article.id == digest.english.article_id), "無")
        print("英文選文：" + selected)
        print(f"LLM：{len(digest.llm_calls)} 個單元，{sum(stat.total_tokens for stat in digest.llm_calls)} tokens，"
              f"{sum(stat.duration_seconds for stat in digest.llm_calls):.1f} 秒")
        for warning in digest.warnings:
            print("警告：" + warning)
        return 0
