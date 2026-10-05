"""Standard-library form transport; errors never retain credential-bearing data."""

from __future__ import annotations

from collections.abc import Callable
from http.client import HTTPException
import json
import math
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import OpenerDirector, Request, build_opener

from .nodes import Node, content_json


class TelegraphError(Exception):
    """A safe API error containing no raw response, request, or access token."""


class TelegraphClient:
    def __init__(self, access_token: str | None = None, *, timeout: float = 30,
                 opener: OpenerDirector | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Telegraph 逾時秒數必須是有限的正數")
        self._access_token = access_token
        self.timeout = timeout
        self._opener = opener if opener is not None else build_opener()
        self._sleep = sleep

    def __repr__(self) -> str:
        return "TelegraphClient(access_token='<已隱藏>')"

    def _request(self, method: str, payload: dict[str, str]) -> dict[str, Any]:
        data = urlencode(payload).encode("utf-8")
        for attempt in range(6):
            result = None
            failure = "Telegraph 網路請求失敗"
            try:
                request = Request(f"https://api.telegra.ph/{method}", data=data,
                                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                                  method="POST")
                with self._opener.open(request, timeout=self.timeout) as response:
                    result = json.loads(response.read())
                    if not 200 <= response.status < 300:
                        failure = "Telegraph HTTP 回應錯誤"
                        if isinstance(result, dict) and result.get("ok") is True:
                            result = None
            except HTTPError as error:
                failure = "Telegraph HTTP 回應錯誤"
                try:
                    result = json.loads(error.read())
                    if isinstance(result, dict) and result.get("ok") is True:
                        result = None
                except (ValueError, UnicodeError, OSError, HTTPException):
                    pass
                finally:
                    error.close()
            except (URLError, OSError, TimeoutError, HTTPException):
                pass
            except (ValueError, UnicodeError):
                failure = "Telegraph API 回應格式無效"
            # Raise outside handlers so urllib's request data is not retained.
            if isinstance(result, dict):
                if result.get("ok") is True:
                    if not isinstance(result.get("result"), dict):
                        raise TelegraphError("Telegraph API 缺少有效結果") from None
                    return result["result"]
                error_code = result.get("error")
                if isinstance(error_code, str):
                    flood = re.fullmatch(r"FLOOD_WAIT_(\d+)", error_code)
                    if flood and attempt < 5:
                        self._sleep(int(flood[1]))
                        continue
                    # Only known-format codes are displayed, never raw prose.
                    if re.fullmatch(r"[A-Z_]+(?:_\d+)?", error_code):
                        safe_code = error_code.replace(self._access_token, "[已隱藏]") if self._access_token else error_code
                        failure = f"Telegraph API 錯誤：{safe_code}"
                    else:
                        failure = "Telegraph API 回應錯誤"
            raise TelegraphError(failure) from None
        raise AssertionError("unreachable")

    def create_account(self, short_name: str = "econ-digest", *, author_name: str = "經濟學人導讀",
                       author_url: str = "") -> dict[str, Any]:
        result = self._request("createAccount", {"short_name": short_name,
                               "author_name": author_name, "author_url": author_url})
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise TelegraphError("Telegraph 帳號缺少存取密鑰")
        return result

    def _page_payload(self, title: str, content: list[Node], author_name: str,
                      author_url: str) -> dict[str, str]:
        if not self._access_token:
            raise ValueError("尚未設定 Telegraph 存取密鑰")
        if not 1 <= len(title) <= 256:
            raise ValueError("Telegraph 標題必須介於 1 與 256 個字元之間")
        encoded = content_json(content)
        if len(encoded.encode("utf-8")) > 64000:
            raise ValueError("Telegraph 內容超過 64000 位元組")
        return {"access_token": self._access_token, "title": title, "content": encoded,
                "author_name": author_name, "author_url": author_url, "return_content": "false"}

    @staticmethod
    def _page(result: dict[str, Any]) -> dict[str, Any]:
        if (not isinstance(result.get("path"), str) or not result["path"]
                or not isinstance(result.get("url"), str) or not result["url"].startswith("https://telegra.ph/")):
            raise TelegraphError("Telegraph 頁面缺少有效路徑或網址")
        return result

    def create_page(self, title: str, content: list[Node], *, author_name: str = "經濟學人導讀",
                    author_url: str = "") -> dict[str, Any]:
        return self._page(self._request("createPage", self._page_payload(title, content, author_name, author_url)))

    def edit_page(self, path: str, title: str, content: list[Node], *,
                  author_name: str = "經濟學人導讀", author_url: str = "") -> dict[str, Any]:
        if not isinstance(path, str) or not path:
            raise ValueError("Telegraph 頁面路徑不得為空")
        result = self._page(self._request(f"editPage/{quote(path, safe='')}",
                           self._page_payload(title, content, author_name, author_url)))
        if result["path"] != path:
            raise TelegraphError("Telegraph 編輯後的頁面路徑已變更")
        return result
