"""One-item scheduler with injected time, durable backoff and private alerts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
import hashlib
import re
from time import sleep
from zoneinfo import ZoneInfo

from ..config import Config, ThreadsConfig
from ..telegram import TelegramClient
from .client import ThreadsClient, ThreadsError
from .formatting import Post
from .queue import Queue
from .tokens import load_token, store_token, timestamp

RENEWAL = ("請到 Meta 應用程式重新授權 threads_basic 與 threads_content_publish，"
           "取得新的長期權杖，更新 ~/.config/econ-digest/env 的 THREADS_ACCESS_TOKEN、"
           "THREADS_USER_ID 與 THREADS_TOKEN_ISSUED_AT，再執行 econ-digest social threads resume。")


def in_window(now: datetime, config: ThreadsConfig) -> bool:
    local = now.astimezone(ZoneInfo(config.timezone)).time().replace(tzinfo=None)
    start, end = time.fromisoformat(config.window_start), time.fromisoformat(config.window_end)
    return start <= local <= end if start < end else local >= start or local <= end


def gate(now: datetime, state: dict, config: ThreadsConfig) -> str | None:
    if not config.enabled:
        return "停用中；social.threads.enabled 必須設為 true 才會發布。"
    if state["paused"]:
        return "佇列已暫停；請先檢查原因，再執行 social threads resume。"
    if not in_window(now, config):
        return "目前不在發文時段。"
    if state.get("next_attempt_at") and now < timestamp(state["next_attempt_at"]):
        return "錯誤退避等待中。"
    if state.get("last_posted_at") and now < timestamp(state["last_posted_at"]) + timedelta(minutes=config.interval_minutes):
        return "尚未達到發文間隔。"
    local_date = now.astimezone(ZoneInfo(config.timezone)).date()
    count = sum(1 for item in state["posts"] if item.get("published_at")
                and timestamp(item["published_at"]).astimezone(ZoneInfo(config.timezone)).date() == local_date)
    if count >= config.max_per_day:
        return "今日已達發文上限。"
    return None


def planned_schedule(now: datetime, count: int, config: ThreadsConfig) -> list[datetime]:
    """Nominal schedule for an empty account/queue, without API quota predictions."""
    cursor = now.astimezone(ZoneInfo(config.timezone)).replace(second=0, microsecond=0)
    if cursor < now:
        cursor += timedelta(minutes=1)
    result = []
    daily: dict = {}
    while len(result) < count:
        if in_window(cursor, config) and daily.get(cursor.date(), 0) < config.max_per_day:
            result.append(cursor)
            daily[cursor.date()] = daily.get(cursor.date(), 0) + 1
            cursor += timedelta(minutes=config.interval_minutes)
        else:
            cursor += timedelta(minutes=1)
    return result


class Scheduler:
    def __init__(self, config: Config, *, clock: Callable[[], datetime] | None = None,
                 client_factory=ThreadsClient, alert: Callable[[str], None] | None = None,
                 wait: Callable[[float], None] = sleep, log: Callable[[str], None] = print) -> None:
        self.config = config
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.client_factory = client_factory
        self.alert = alert
        self.wait = wait
        self.log = log
        self.queue = Queue(config.paths.data_dir)

    def _alert_once(self, state: dict, kind: str, message: str) -> None:
        if kind in state["alerts"]:
            return
        # Persist before sending. If Telegram's response is lost, never retry an
        # alert that may already have arrived in the private chat.
        state["alerts"][kind] = "attempted"
        self.queue.save(state)
        secret = self.config.secrets
        try:
            if self.alert:
                self.alert(message)
            elif (secret.telegram_bot_token and secret.telegram_chat_id
                  and re.fullmatch(r"[1-9][0-9]*", secret.telegram_chat_id)):
                TelegramClient(secret.telegram_bot_token).send_message_safe(secret.telegram_chat_id, message)
            else:
                state["alerts"][kind] = "unavailable"
                self.log("私人警示未設定；請以 telegram-setup 設定私人聊天室。")
                self.queue.save(state)
                return
        except Exception:
            state["alerts"][kind] = "failed"
            self.log("私人 Telegram 警示傳送失敗；請檢查私人聊天室設定。")
        else:
            state["alerts"][kind] = "sent"
        self.queue.save(state)

    def _stop(self, state: dict, kind: str, message: str) -> None:
        state["paused"] = True
        state["pause_reason"] = kind
        self.queue.save(state)
        self._alert_once(state, kind, message)

    def _backoff(self, state: dict, now: datetime, error: ThreadsError) -> None:
        state["failures"] = state.get("failures", 0) + 1
        delay = max(error.retry_after or 0, min(21600, 60 * 2 ** min(state["failures"] - 1, 9)))
        state["next_attempt_at"] = (now + timedelta(seconds=delay)).isoformat()
        self.queue.save(state)

    def _posted(self, state: dict, record: dict, post_id: str, stamp: str) -> None:
        record.update(status="posted", post_id=post_id, published_at=stamp)
        state.update(last_posted_at=stamp, next_attempt_at=None, failures=0)
        self.queue.save(state)

    def post_next(self, *, dry_run: bool = False) -> int:
        with self.queue.lock():
            return self._post_next(dry_run=dry_run)

    def _post_next(self, *, dry_run: bool) -> int:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("排程時鐘必須包含時區。")
        now = now.astimezone(timezone.utc)
        state = self.queue.load()
        record = self.queue.next(state)
        reason = gate(now, state, self.config.social.threads)
        if dry_run:
            self.log("離線試跑；" + (reason or "本機排程條件通過，實際發布仍須查詢 API 額度。"))
            if record:
                self.log(record["post"]["text"])
            else:
                self.log("佇列沒有待發布貼文。")
            return 0
        if reason:
            self.log(reason)
            return 0
        token = load_token(self.config, now)
        if token is None:
            if not record:
                self.log("佇列沒有待發布貼文。")
                return 0
            self.log("尚未設定 Threads：請在私人 env 檔填入 THREADS_ACCESS_TOKEN 與 THREADS_USER_ID。")
            return 2
        if not record and token.age_days(now) < 50:
            self.log("佇列沒有待發布貼文。")
            return 0
        account_hash = hashlib.sha256(token.user_id.encode()).hexdigest()
        if state.get("account_hash") not in (None, account_hash):
            self._stop(state, "account", "Threads 帳號已變更，佇列仍屬於原帳號。請保留發布紀錄並檢查設定。")
            self.log("Threads 帳號與佇列紀錄不符，已暫停。")
            return 1
        state["account_hash"] = account_hash
        self.queue.save(state)
        store_token(self.config, token)
        client = self.client_factory(token.access_token, token.user_id, clock=self.clock)
        if token.age_days(now) >= 50:
            try:
                refreshed, expires = client.refresh_token()
            except ThreadsError as error:
                self._stop(state, "refresh", "Threads 權杖更新失敗，發文已暫停。" + RENEWAL)
                self.log("Threads 權杖更新失敗，已暫停；請更新私人 env 檔後 resume。")
                return 1
            token = replace(token, access_token=refreshed, issued_at=now,
                            expires_at=now + timedelta(seconds=expires), age_estimated=False)
            store_token(self.config, token)
            client = self.client_factory(token.access_token, token.user_id, clock=self.clock)
        if not record:
            self.log("權杖已更新；佇列沒有待發布貼文。")
            return 0
        post = Post(**record["post"])
        try:
            if client.remaining_quota() <= 0:
                self._backoff(state, now, ThreadsError(retry_after=3600))
                self.log("Threads API 發布額度已用完，稍後再試。")
                return 0
            if record["status"] == "uncertain":
                self._stop(state, "uncertain", "Threads 發布結果待確認，佇列已暫停，請檢查帳號貼文與本機容器紀錄。")
                return 1
            if record["container_id"]:
                status = client.container_status(record["container_id"])
                if status == "PUBLISHED":
                    found = client.find_published(post, timestamp(record["publish_started_at"]))
                    if found:
                        self._posted(state, record, *found)
                        self.log("已恢復先前發布紀錄。")
                        return 0
                    record["status"] = "uncertain"
                    self._stop(state, "uncertain", "Threads 已發布，但找不到唯一貼文紀錄；請人工核對，佇列已暫停以避免重複發布。")
                    return 1
                if status == "IN_PROGRESS":
                    self._backoff(state, now, ThreadsError(retry_after=60))
                    return 0
                if status in ("ERROR", "EXPIRED"):
                    if record["status"] == "publishing":
                        record["status"] = "uncertain"
                        self._stop(state, "uncertain", "Threads 容器已失效，先前發布結果待確認；請人工核對帳號，佇列已暫停。")
                        return 1
                    record.update(container_id=None, status="pending")
                    self.queue.save(state)
            if not record["container_id"]:
                record.update(container_id=client.create_container(post), status="container", created_at=now.isoformat())
                self.queue.save(state)
                # Official documentation recommends averaging 30 seconds.
                self.wait(30)
            record.update(status="publishing", publish_started_at=now.isoformat())
            self.queue.save(state)
            identifier = client.publish_container(record["container_id"])
            self._posted(state, record, identifier, self.clock().astimezone(timezone.utc).isoformat())
            self.log("已發布 1 則 Threads 貼文。")
            return 0
        except ThreadsError as error:
            if error.authorization:
                self._stop(state, "authorization", "Threads 授權失效或權限不足，發文已暫停。" + RENEWAL)
            else:
                # A definitive rejection may safely reuse the container. An
                # ambiguous publish stays 'publishing' for reconciliation.
                if record["status"] == "publishing" and not error.ambiguous:
                    record["status"] = "container"
                self._backoff(state, now, error)
            self.log("Threads 發布失敗，" + ("已暫停並記錄私人警示。" if error.authorization else "已記錄退避時間。"))
            return 1
