"""Render a saved digest without network or LLM calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import Config
from ..fetch import issue_directory, normalize_issue_date
from ..models import Digest, load_json
from ..render import write_outputs
from ..site import build_site
from . import add_issue_argument


def saved_issue_directory(config: Config, issue_spec: str = "latest") -> Path:
    if issue_spec != "latest":
        return issue_directory(config, normalize_issue_date(issue_spec))
    candidates = sorted((config.paths.data_dir / "issues").glob("te_*/digest.json"))
    if not candidates:
        raise FileNotFoundError("找不到 digest.json；請先執行 econ-digest run --no-send")
    return candidates[-1].parent


def configure(parser: argparse.ArgumentParser) -> None:
    add_issue_argument(parser)


def run(args: argparse.Namespace, config: Config) -> int:
    try:
        directory = saved_issue_directory(config, args.issue)
        digest = load_json(directory / "digest.json", Digest)
        paths = write_outputs(digest, directory, embed_images=config.report.embed_images)
        epub = directory / f"TheEconomist.{digest.issue_date}.epub"
        site = build_site(digest, config.paths.output_dir, epub)
        print(f"私人網站：{site.pages['index']}")
        for label, path in paths.items():
            print(f"{label}：{path}")
        messages = json.loads(paths["telegram"].read_text(encoding="utf-8"))
        print(f"Telegram 訊息：{len(messages)} 則")
        return 0
    except Exception as error:
        print(f"報告產生失敗（{type(error).__name__}）；請確認已完成分析且 digest.json 可讀取。")
        return 1
