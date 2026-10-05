"""Locked, cached weekly fetch-to-delivery workflow."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
from typing import Any, cast
from zoneinfo import ZoneInfo

from .commands.send import send_digest
from .config import Config
from .epub_parser import parse_epub
from .fetch import Fetcher, issue_directory, issue_url
from .models import Digest, Issue, load_json, save_json
from .logutil import redact
from .render import write_outputs
from .site import build_site
from .site.backup import backup_output
from .state import AlreadyRunning, State, load_state, run_lock, save_state, utc_now
from .telegram import TelegramClient

logger = logging.getLogger(__name__)


def _analyze(issue: Issue, config: Config, state: State, progress: Callable[[str], None]) -> Digest:
    from .analysis.pipeline import analyze_issue, make_llm_client

    return analyze_issue(issue, config, make_llm_client(config),
                         workdir=issue_directory(config, issue.issue_date) / "analysis",
                         english_history=state["english_history"][-8:], progress=progress)


def _send(config: Config, issue_date: str, *, force: bool, log: Callable[[str], None]) -> int:
    return send_digest(config, issue_date, force=force, log=log)


def _error_notice(config: Config, state: State, issue_date: str | None, error_type: str,
                  log: Callable[[str], None]) -> None:
    token, chat_id = config.secrets.telegram_bot_token, config.secrets.telegram_chat_id
    if not config.telegram.enabled or not token or not chat_id:
        return
    today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    notices = cast(dict[str, Any], state).setdefault("error_notices", {})
    key = issue_date or "latest"
    if notices.get(key) == today:
        return
    # Persist the attempt first so repeated failures cannot flood the chat.
    notices[key] = today
    save_state(config.paths.data_dir, state)
    try:
        TelegramClient(token, min_interval=config.telegram.message_delay_seconds).send_message_safe(
            chat_id, f"⚠️ 本週經濟學人導讀產生失敗（{error_type}），稍後會自動重試。")
    except Exception as notice_error:
        log(f"失敗通知無法傳送（{type(notice_error).__name__}）。")


def _run_locked(config: Config, issue_spec: str, *, no_send: bool, dry_run: bool,
                force: bool, reanalyze: bool, log: Callable[[str], None]) -> int:
    date: str | None = None
    started = utc_now()
    try:
        state = load_state(config.paths.data_dir)
        state["last_run"] = {"started_at": started, "finished_at": None, "issue_date": None,
                             "outcome": "running", "error": None}
        save_state(config.paths.data_dir, state)
        fetcher = Fetcher(config)
        date = fetcher.resolve_issue(issue_spec)
        state["last_run"]["issue_date"] = date
        save_state(config.paths.data_dir, state)
        if date in state["delivered"] and not force:
            log("沒有新的一期")
            outcome = "nothing_new"
        else:
            directory = issue_directory(config, date)
            digest_path = directory / "digest.json"
            if digest_path.exists() and not reanalyze:
                digest = load_json(digest_path, Digest)
                log(f"使用已完成的分析：{date}")
            else:
                log(f"下載期別：{date}")
                epub = fetcher.download_issue(date)
                issue_path = directory / "issue.json"
                issue = load_json(issue_path, Issue) if issue_path.exists() else parse_epub(epub, date, issue_url(date, config))
                save_json(issue_path, issue)
                digest = _analyze(issue, config, state, log)
                save_json(digest_path, digest)
            paths = write_outputs(digest, directory, embed_images=config.report.embed_images)
            ready = config.secrets.telegram_bot_token and config.secrets.telegram_chat_id
            if no_send or dry_run or not config.telegram.enabled or not ready:
                if not dry_run:
                    build_site(digest, config.paths.output_dir, directory / f"TheEconomist.{date}.epub")
                backup_output(config.paths.output_dir, config.backup, date, config.paths.data_dir,
                              dry_run=dry_run, log=log)
                log(f"報告已產生：{paths['html']}")
            elif _send(config, date, force=force, log=log) != 0:
                raise RuntimeError("Telegram 傳送未完成")
            outcome = "success"
        state = load_state(config.paths.data_dir)
        state["last_run"].update(finished_at=utc_now(), outcome=outcome, error=None)
        save_state(config.paths.data_dir, state)
        return 0
    except Exception as error:
        error_type = type(error).__name__
        log(f"導讀產生失敗（{error_type}），稍後可重新執行。")
        try:
            state = load_state(config.paths.data_dir)
            state["last_run"] = {"started_at": started, "finished_at": utc_now(), "issue_date": date,
                                 "outcome": "failed", "error": error_type}
            save_state(config.paths.data_dir, state)
            _error_notice(config, state, date, error_type, log)
        except Exception as state_error:
            log(f"無法記錄執行狀態（{type(state_error).__name__}）。")
        return 1


def run_pipeline(config: Config, issue_spec: str = "latest", *, no_send: bool = False,
                 dry_run: bool = False, force: bool = False, reanalyze: bool = False,
                 log: Callable[[str], None] | None = None) -> int:
    output = log or logger.info

    def progress(message: str) -> None:
        output(redact(message, config.secrets))
    try:
        with run_lock(config.paths.data_dir):
            return _run_locked(config, issue_spec, no_send=no_send, dry_run=dry_run,
                               force=force, reanalyze=reanalyze, log=progress)
    except AlreadyRunning:
        progress("已有 econ-digest 程序正在執行，本次略過。")
        return 0
    except OSError as error:
        progress(f"無法取得執行鎖（{type(error).__name__}）。")
        return 1
