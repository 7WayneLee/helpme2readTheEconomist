"""Resumable Telegram delivery with issue-level idempotency."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable

from ..config import Config
from ..models import Digest, load_json, save_json
from ..state import AlreadyRunning, load_state, run_lock, save_state, utc_now
from ..telegram import TelegramClient
from ..telegram.format import check_html, utf16_len
from . import add_issue_argument
from .render import saved_issue_directory

SETUP_INSTRUCTIONS = ("尚未設定 Telegram：請在 ~/.config/econ-digest/env 填入 TELEGRAM_BOT_TOKEN，"
                      "再執行 econ-digest telegram-setup 設定 TELEGRAM_CHAT_ID。")


def send_digest(config: Config, issue_spec: str = "latest", *, force: bool = False,
                dry_run: bool = False, log: Callable[[str], None] = print) -> int:
    token, chat_id = config.secrets.telegram_bot_token, config.secrets.telegram_chat_id
    if not dry_run and (not token or not chat_id):
        log(SETUP_INSTRUCTIONS)
        return 2
    directory = saved_issue_directory(config, issue_spec)
    digest = load_json(directory / "digest.json", Digest)
    state = load_state(config.paths.data_dir)
    if digest.issue_date in state["delivered"] and not force:
        log("本期已傳送；如需再次傳送，請加上 --force。")
        return 0
    messages = json.loads((directory / "telegram_messages.json").read_text(encoding="utf-8"))
    if not isinstance(messages, list) or not all(isinstance(message, str) for message in messages):
        raise ValueError("telegram_messages.json 必須是字串陣列")
    for message in messages:
        check_html(message)
        if utf16_len(message) > 4000:
            raise ValueError("Telegram 訊息超過 4000 個 UTF-16 單位；請重新 render")
    if dry_run:
        for index, message in enumerate(messages, 1):
            log(f"--- 訊息 {index}/{len(messages)} ---\n{message}")
        return 0
    assert token is not None and chat_id is not None
    report_path = directory / "report.html"
    report_bytes = report_path.read_bytes() if config.telegram.send_report_file else b""
    fingerprint = hashlib.sha256(json.dumps([messages, chat_id, config.telegram.send_report_file], ensure_ascii=False).encode("utf-8") + report_bytes).hexdigest()
    progress_path = directory / "telegram_progress.json"
    progress = {"fingerprint": fingerprint, "next_message": 0, "document_sent": False}
    if progress_path.exists() and not force:
        previous = json.loads(progress_path.read_text(encoding="utf-8"))
        if previous.get("fingerprint") != fingerprint:
            raise ValueError("報告或聊天室已變更；請確認後使用 --force 重新傳送")
        progress = previous
    next_message = progress["next_message"]
    if type(next_message) is not int or not 0 <= next_message <= len(messages):
        raise ValueError("telegram_progress.json 的傳送進度無效")
    client = TelegramClient(token, min_interval=config.telegram.message_delay_seconds)
    for index in range(next_message, len(messages)):
        client.send_message_safe(chat_id, messages[index])
        progress["next_message"] = index + 1
        save_json(progress_path, progress)
    if config.telegram.send_report_file and not progress["document_sent"]:
        client.send_document(chat_id, report_path, caption_html="完整報告（含英文選文原文）")
        progress["document_sent"] = True
        save_json(progress_path, progress)
    state["delivered"][digest.issue_date] = {"delivered_at": utc_now(), "message_count": len(messages)}
    if digest.english:
        article = next((item for item in digest.issue.articles if item.id == digest.english.article_id), None)
        if article:
            record = {"issue_date": digest.issue_date, "article_id": article.id, "section": article.section,
                      "kind": article.kind, "title": article.title}
            if record not in state["english_history"]:
                state["english_history"].append(record)
    save_state(config.paths.data_dir, state)
    log(f"已傳送 {len(messages)} 則訊息。")
    return 0


def configure(parser: argparse.ArgumentParser) -> None:
    add_issue_argument(parser)
    parser.add_argument("--force", action="store_true", help="重新傳送本期所有訊息")
    parser.add_argument("--dry-run", action="store_true", help="列印訊息內容")


def run(args: argparse.Namespace, config: Config) -> int:
    try:
        with run_lock(config.paths.data_dir):
            return send_digest(config, args.issue, force=args.force, dry_run=args.dry_run)
    except AlreadyRunning:
        print("已有 econ-digest 程序正在執行。")
        return 0
    except Exception as error:
        print(f"傳送失敗（{type(error).__name__}）；再次執行 send 可接續傳送。")
        return 1
