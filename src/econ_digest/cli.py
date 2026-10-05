"""CLI registry: new command modules require no changes to this file."""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Sequence

from .config import Config, ConfigError, load_config
from .epub_parser import EpubParseError
from .fetch import FetchError
from .logutil import configure_logging, redact
from .state import AlreadyRunning, StateError

COMMANDS = ("fetch", "parse", "signals", "analyze", "render", "send", "run", "telegram-setup")
COMMAND_HELP = {
    "fetch": "下載 EPUB", "parse": "解析文章並儲存快取", "signals": "列出台灣相關詞彙",
    "analyze": "分析文章並產生摘要", "render": "產生 Markdown 與 HTML 報告",
    "send": "推送報告到 Telegram", "run": "執行完整流程", "telegram-setup": "設定 Telegram 私人聊天室",
}


def _unimplemented(args: argparse.Namespace, config: Config) -> int:
    print("此功能尚未實作", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="econ-digest", description="每週 Economist 台灣讀者摘要")
    parser.add_argument("--config", metavar="PATH", help="TOML 設定檔路徑")
    parser.add_argument("-v", "--verbose", action="store_true", help="顯示詳細日誌")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        module_name = f"econ_digest.commands.{name.replace('-', '_')}"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
            subparser = commands.add_parser(name, help="（尚未實作）")
            subparser.set_defaults(_run=_unimplemented)
        else:
            subparser = commands.add_parser(name, help=COMMAND_HELP[name])
            module.configure(subparser)
            subparser.set_defaults(_run=module.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config: Config | None = None
    try:
        config = load_config(args.config)
        configure_logging(config, args.verbose)
        return args._run(args, config)
    except (ConfigError, FetchError, EpubParseError, AlreadyRunning, StateError, OSError) as exc:
        print(f"錯誤：{redact(str(exc), config.secrets if config else None)}", file=sys.stderr)
        return 1
