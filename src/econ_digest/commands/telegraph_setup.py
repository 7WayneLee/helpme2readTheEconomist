"""Create a Telegraph account and persist its secret without displaying it."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import os
from pathlib import Path

from ..config import Config
from ..telegraph import TelegraphClient, TelegraphError
from .telegram_setup import update_env_value


def ensure_account(config: Config, *, force: bool = False,
                   log: Callable[[str], None] = print) -> str:
    existing = config.secrets.telegraph_access_token
    if existing and not force:
        log(f"Telegraph 帳號：econ-digest｜作者：{config.telegraph.author_name}")
        return existing
    account = TelegraphClient().create_account("econ-digest", author_name=config.telegraph.author_name,
                                               author_url=config.telegraph.author_url)
    token = account.get("access_token")
    if not isinstance(token, str) or not token:
        raise TelegraphError("Telegraph 帳號缺少存取密鑰")
    path = Path(os.environ.get("ECON_DIGEST_ENV_FILE", "~/.config/econ-digest/env")).expanduser()
    update_env_value(path, "TELEGRAPH_ACCESS_TOKEN", token)
    # Account metadata can be supplied by an untrusted API; print configured names only.
    log(f"Telegraph 帳號：econ-digest｜作者：{config.telegraph.author_name}")
    return token


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--force", action="store_true", help="建立新帳號並取代現有密鑰")


def run(args: argparse.Namespace, config: Config) -> int:
    try:
        ensure_account(config, force=args.force)
        return 0
    except Exception as error:
        print(f"Telegraph 設定失敗（{type(error).__name__}）。")
        return 1
