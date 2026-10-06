"""Threads Graph transport. Every failure is sanitized before leaving this module."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .formatting import Post, character_count


class ThreadsError(Exception):
    def __init__(self, status: int | None = None, *, code: int | None = None,
                 retry_after: float | None = None, ambiguous: bool = False) -> None:
        self.status = status
        self.code = code
        self.retry_after = retry_after
        self.ambiguous = ambiguous
        self.authorization = status in (401, 403) or code in (10, 102, 190, 200)
        super().__init__("Threads 授權失效或權限不足。" if self.authorization else "Threads API 請求失敗。")


def retry_after_seconds(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - now).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


class ThreadsClient:
    def __init__(self, token: str, user_id: str, *, opener=None, timeout: float = 30,
                 clock=None) -> None:
        if not token or not re.fullmatch(r"[A-Za-z0-9_-]+", user_id):
            raise ValueError("Threads 權杖或帳號設定無效。")
        self._token, self._user_id = token, user_id
        self._opener = opener if opener is not None else build_opener()
        self.timeout = timeout
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return "ThreadsClient(憑證已隱藏)"

    def _request(self, method: str, path: str, params: dict, *, root: bool = False) -> dict:
        params = {**params, "access_token": self._token}
        base = "https://graph.threads.net" + ("" if root else "/v1.0")
        encoded = urlencode(params).encode("utf-8")
        url = f"{base}/{path}"
        request = Request(url + ("?" + encoded.decode() if method == "GET" else ""),
                          data=encoded if method == "POST" else None, method=method,
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                status = getattr(response, "status", 200)
                headers = response.headers
                payload = response.read()
        except HTTPError as exc:
            status, headers, payload = exc.code, exc.headers, exc.read()
        except (URLError, OSError, HTTPException, ValueError):
            raise ThreadsError(ambiguous=method == "POST") from None
        try:
            data = json.loads(payload)
        except (ValueError, UnicodeError):
            raise ThreadsError(status, ambiguous=method == "POST") from None
        if not isinstance(data, dict) or status >= 400 or "error" in data:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            code = error.get("code") if isinstance(error, dict) else None
            raise ThreadsError(status, code=code if type(code) is int else None,
                               retry_after=retry_after_seconds(headers.get("Retry-After"), self._clock()),
                               ambiguous=method == "POST" and status >= 500) from None
        return data

    def remaining_quota(self) -> int:
        data = self._request("GET", f"{self._user_id}/threads_publishing_limit", {"fields": "quota_usage,config"})
        try:
            record = data["data"][0]
            total, used = record["config"]["quota_total"], record["quota_usage"]
            if type(total) is not int or type(used) is not int or total < 0 or used < 0:
                raise ValueError
            return max(0, total - used)
        except (KeyError, TypeError, IndexError, ValueError):
            raise ThreadsError() from None

    def create_container(self, post: Post) -> str:
        if character_count(post.text) > 500:
            raise ValueError("Threads 貼文超過 500 字元。")
        params = {"media_type": "IMAGE" if post.image_url else "TEXT", "text": post.text}
        if post.image_url:
            params["image_url"] = post.image_url
        else:
            params["link_attachment"] = post.link_url
        data = self._request("POST", f"{self._user_id}/threads", params)
        identifier = data.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ThreadsError(ambiguous=True)
        return identifier

    def publish_container(self, container_id: str) -> str:
        data = self._request("POST", f"{self._user_id}/threads_publish", {"creation_id": container_id})
        identifier = data.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ThreadsError(ambiguous=True)
        return identifier

    def container_status(self, container_id: str) -> str:
        data = self._request("GET", container_id, {"fields": "status,error_message"})
        status = data.get("status")
        if status not in ("EXPIRED", "ERROR", "FINISHED", "IN_PROGRESS", "PUBLISHED"):
            raise ThreadsError()
        return status

    def find_published(self, post: Post, started_at: datetime) -> tuple[str, str] | None:
        # Recover a lost publish response from our own posts, using exact text and
        # timestamp. Pagination uses cursors, never a server-supplied URL/token.
        params = {"fields": "id,text,timestamp", "limit": 100}
        matches = []
        for _ in range(5):
            data = self._request("GET", f"{self._user_id}/threads", params)
            try:
                for item in data["data"]:
                    stamp = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                    if item.get("text") == post.text and stamp >= started_at:
                        matches.append((item["id"], stamp.isoformat()))
                cursor = data.get("paging", {}).get("cursors", {}).get("after")
                if not data.get("paging", {}).get("next") or not cursor:
                    break
                params["after"] = cursor
            except (KeyError, TypeError, ValueError):
                raise ThreadsError() from None
        return matches[0] if len(matches) == 1 else None

    def refresh_token(self) -> tuple[str, int]:
        data = self._request("GET", "refresh_access_token", {"grant_type": "th_refresh_token"}, root=True)
        token, expires = data.get("access_token"), data.get("expires_in")
        if not isinstance(token, str) or not token or type(expires) is not int or expires <= 0:
            raise ThreadsError()
        return token, expires
