"""Offline previews and opt-in scheduled Threads publishing."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from ..config import Config
from ..social.formatting import Post, character_count
from ..social.queue import Queue, prepare_posts
from ..social.scheduler import Scheduler
from ..social.tokens import load_token
from .render import saved_issue_directory


def configure(parser: argparse.ArgumentParser) -> None:
    platforms = parser.add_subparsers(dest="social_platform", required=True)
    threads = platforms.add_parser("threads", help="Threads 發文")
    actions = threads.add_subparsers(dest="social_action", required=True)
    preview = actions.add_parser("preview", help="離線預覽每則貼文與字數")
    preview.add_argument("--issue", default="latest", metavar="YYYY.MM.DD")
    enqueue = actions.add_parser("enqueue", help="將已發布期號加入佇列")
    enqueue.add_argument("--issue", required=True, metavar="YYYY.MM.DD")
    next_post = actions.add_parser("post-next", help="依排程發布至多一則貼文")
    next_post.add_argument("--dry-run", action="store_true", help="離線試跑，不查詢 API 或傳送警示")
    actions.add_parser("status", help="佇列進度與權杖年齡")
    actions.add_parser("pause", help="暫停佇列")
    actions.add_parser("resume", help="恢復佇列並重設警示與退避")


def run(args: argparse.Namespace, config: Config) -> int:
    action = args.social_action
    queue = Queue(config.paths.data_dir)
    try:
        if action in ("preview", "enqueue"):
            directory = saved_issue_directory(config, args.issue)
            # Frozen queued text is what will be published, even if the
            # underlying digest or settings have since been edited.
            stored = [Post(**record["post"]) for record in queue.load()["posts"]
                      if record["post"]["issue_date"] == directory.name.removeprefix("te_")]
            posts = stored if action == "preview" and stored else prepare_posts(
                directory, config.social.threads, preview=action == "preview",
                page_limit_bytes=config.telegraph.page_limit_bytes)
            if action == "enqueue":
                print(f"已加入 {queue.enqueue(posts)} 則貼文；既有紀錄保留。")
            else:
                for index, post in enumerate(posts, 1):
                    print(f"[{index}/{len(posts)}] {post.section}｜{character_count(post.text)}/500 字元")
                    print(post.text + "\n")
                print(f"共 {len(posts)} 則貼文（含 1 則本期介紹）。")
            return 0
        if action == "post-next":
            return Scheduler(config).post_next(dry_run=args.dry_run)
        if action in ("pause", "resume"):
            with queue.lock():
                state = queue.load()
                state["paused"] = action == "pause"
                if action == "resume":
                    state.update(alerts={}, failures=0, next_attempt_at=None, pause_reason=None)
                queue.save(state)
            print("佇列已暫停。" if action == "pause" else "佇列已恢復；仍須啟用設定才會發布。")
            return 0
        state = queue.load()
        posted = sum(p["status"] == "posted" for p in state["posts"])
        print(f"Threads：{'啟用' if config.social.threads.enabled else '停用'}；佇列：{'暫停' if state['paused'] else '可執行'}")
        print(f"已發布 {posted}/{len(state['posts'])} 則；待發布 {len(state['posts']) - posted} 則。")
        if state.get("pause_reason"):
            labels = {"authorization": "授權失效", "refresh": "權杖更新失敗", "account": "帳號不符", "uncertain": "發布結果待確認"}
            print("暫停原因：" + labels.get(state["pause_reason"], "人工暫停"))
        if state.get("next_attempt_at"):
            print("下次可重試：" + state["next_attempt_at"])
        now = datetime.now(timezone.utc)
        token = load_token(config, now)
        print("權杖：尚未設定。" if token is None else
              f"權杖年齡：{token.age_days(now):.1f} 天{'（依 env 檔時間估計）' if token.age_estimated else ''}；到期：{token.expires_at.date()}。")
        return 0
    except Exception as error:
        # Never stringify exceptions from secret-bearing storage/transports.
        print(f"社群操作失敗（{type(error).__name__}）；請檢查本期資料、公開封面與佇列狀態。")
        return 1
