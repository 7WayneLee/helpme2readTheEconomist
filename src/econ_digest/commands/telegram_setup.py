"""Discover a private bot chat and securely update the secrets file."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import tempfile
import time

from ..config import Config
from ..telegram import TelegramClient, discover_private_chats


def update_chat_id(path: Path, chat_id: str) -> None:
    if not re.fullmatch(r"-?\d+", chat_id):
        raise ValueError("TELEGRAM_CHAT_ID 必須是數字")
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = path.read_text(encoding="utf-8") if path.exists() else ""
    result: list[str] = []
    replaced = False
    for line in contents.splitlines(keepends=True):
        if re.match(r"\s*TELEGRAM_CHAT_ID\s*=", line):
            if not replaced:
                result.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
                replaced = True
        else:
            result.append(line)
    if not replaced:
        if result and not result[-1].endswith("\n"):
            result[-1] += "\n"
        result.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".env.", delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write("".join(result))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--chat-id", help="直接指定私人聊天室 ID")
    parser.add_argument("--test", action="store_true", help="傳送設定完成訊息")
    parser.add_argument("--wait", type=float, default=120, metavar="SECONDS", help="等候 /start 的秒數（預設 120）")


def run(args: argparse.Namespace, config: Config) -> int:
    token = config.secrets.telegram_bot_token
    if not token:
        print("請先在 ~/.config/econ-digest/env 填入 TELEGRAM_BOT_TOKEN，再執行 econ-digest telegram-setup。")
        return 2
    if not 0 <= args.wait < float("inf"):
        print("--wait 必須是有限的非負秒數。")
        return 2
    try:
        client = TelegramClient(token, min_interval=config.telegram.message_delay_seconds)
        identity = client.get_me()
        print(f"機器人：@{identity.get('username', 'unknown')}")
        chat_id = args.chat_id
        if chat_id is None:
            print("請開啟機器人的私人聊天室並傳送 /start。", flush=True)
            deadline = time.monotonic() + args.wait
            while True:
                chats = discover_private_chats(client)
                if chats:
                    for chat in chats:
                        print(f"找到私人聊天室：{chat['chat_id']}（{chat.get('first_name') or chat.get('username') or '未提供名稱'}）")
                    if len(chats) > 1:
                        print("找到多個私人聊天室；請使用 --chat-id ID 指定要接收報告的聊天室。")
                        return 2
                    chat_id = str(chats[0]["chat_id"])
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    print("尚未收到 /start；請傳送後再次執行 telegram-setup。")
                    return 2
                time.sleep(min(2, remaining))
        path = Path(os.environ.get("ECON_DIGEST_ENV_FILE", "~/.config/econ-digest/env")).expanduser()
        update_chat_id(path, str(chat_id))
        print(f"已更新 TELEGRAM_CHAT_ID：{path}（權限 600）")
        if args.test:
            client.send_message_safe(str(chat_id), "✅ 經濟學人導讀機器人設定完成")
        return 0
    except Exception as error:
        print(f"Telegram 設定失敗（{type(error).__name__}）。")
        return 1
