"""Standard-library Telegram Bot API transport with secret-safe failures."""

from __future__ import annotations

from collections.abc import Callable
from http.client import HTTPException
import json
import logging
import math
import mimetypes
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import OpenerDirector, Request, build_opener
import uuid

from .format import strip_tags


_LOGGER = logging.getLogger(__name__)
ChatId = int | str


class TelegramError(Exception):
    """A sanitized API error; status is None when no HTTP response arrived."""

    def __init__(self, status: int | None, description: str) -> None:
        self.status = status
        self.description = description
        super().__init__(f"Telegram error {status if status is not None else 'network'}: {description}")


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.telegram.org",
        timeout: float = 30,
        min_interval: float = 1.1,
        opener: OpenerDirector | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not token:
            raise ValueError("Telegram bot token must not be empty")
        parsed_base = urlsplit(api_base)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise ValueError("Telegram API base must be an HTTP(S) URL")
        if parsed_base.query or parsed_base.fragment or parsed_base.username:
            raise ValueError("Telegram API base must not contain credentials, query, or fragment")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Telegram timeout must be positive and finite")
        if not math.isfinite(min_interval) or min_interval < 0:
            raise ValueError("Telegram minimum interval must be nonnegative and finite")
        self._token = token
        self._api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.min_interval = min_interval
        self._opener = opener if opener is not None else build_opener()
        self._sleep = sleep
        self._clock = clock
        self._last_send: float | None = None

    def __repr__(self) -> str:
        return f"TelegramClient(api_base={self._redact(self._api_base)!r}, token='<redacted>')"

    def _redact(self, text: str) -> str:
        return text.replace(f"bot{self._token}", "bot<redacted>").replace(self._token, "<redacted>")

    def _pace(self) -> None:
        if self._last_send is not None:
            remaining = self.min_interval - (self._clock() - self._last_send)
            if remaining > 0:
                self._sleep(remaining)
        self._last_send = self._clock()

    @staticmethod
    def _decode(body: bytes) -> dict[str, Any] | None:
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError):
            return None
        return value if isinstance(value, dict) else None

    def _request(
        self,
        method: str,
        data: bytes,
        content_type: str = "application/json",
        *,
        sending: bool = False,
    ) -> Any:
        rate_retries = 0
        transient_retries = 0
        while True:
            if sending:
                self._pace()
            status: int | None = None
            response_data: dict[str, Any] | None = None
            description = ""
            invalid_request = False
            try:
                request = Request(
                    f"{self._api_base}/bot{self._token}/{method}",
                    data=data,
                    headers={"Content-Type": content_type},
                    method="POST",
                )
                with self._opener.open(request, timeout=self.timeout) as response:
                    status = response.status
                    response_data = self._decode(response.read())
            except HTTPError as error:
                status = error.code
                description = self._redact(str(error))
                try:
                    response_data = self._decode(error.read())
                except (URLError, OSError, TimeoutError, HTTPException):
                    pass
                finally:
                    error.close()
            except (URLError, OSError, TimeoutError, HTTPException) as error:
                status = None
                response_data = None
                description = self._redact(str(error))
            except (ValueError, UnicodeError) as error:
                description = self._redact(str(error))
                invalid_request = True

            # Raise outside the except block: no urllib exception containing
            # the credential-bearing URL is retained as an exception context.
            if invalid_request:
                raise TelegramError(status, description) from None
            if response_data is not None:
                if status is not None and 200 <= status < 300 and response_data.get("ok") is True:
                    if "result" not in response_data:
                        raise TelegramError(status, "API response is missing its result") from None
                    return response_data["result"]
                api_status = response_data.get("error_code")
                if (
                    status is not None
                    and 200 <= status < 300
                    and isinstance(api_status, int)
                    and not isinstance(api_status, bool)
                ):
                    status = api_status
                description = self._redact(str(response_data.get("description") or description))
            if not description:
                description = "Invalid Telegram API response"

            if status == 429 and rate_retries < 5:
                parameters = response_data.get("parameters") if response_data else None
                retry_after = parameters.get("retry_after", 1) if isinstance(parameters, dict) else 1
                if (
                    not isinstance(retry_after, (int, float))
                    or not math.isfinite(retry_after)
                    or retry_after < 0
                ):
                    retry_after = 1
                self._sleep(float(retry_after) + 0.5)
                rate_retries += 1
                continue
            if (status is None or 500 <= status <= 599) and transient_retries < 4:
                self._sleep(float(2 ** (transient_retries + 1)))
                transient_retries += 1
                continue
            raise TelegramError(status, self._redact(description)) from None

    def _json_request(self, method: str, payload: dict[str, Any], *, sending: bool = False) -> Any:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._request(method, data, sending=sending)

    def get_me(self) -> dict[str, Any]:
        result = self._json_request("getMe", {})
        if not isinstance(result, dict):
            raise TelegramError(200, "Invalid getMe result")
        return result

    def get_updates(self, offset: int | None = None, timeout: int = 0) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        result = self._json_request("getUpdates", payload)
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise TelegramError(200, "Invalid getUpdates result")
        return result

    def get_chat(self, chat_id: ChatId) -> dict[str, Any]:
        result = self._json_request("getChat", {"chat_id": chat_id})
        if not isinstance(result, dict):
            raise TelegramError(200, "Invalid getChat result")
        return result

    def get_chat_member(self, chat_id: ChatId, user_id: int) -> dict[str, Any]:
        result = self._json_request("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        if not isinstance(result, dict):
            raise TelegramError(200, "Invalid getChatMember result")
        return result

    @staticmethod
    def _message_id(result: Any) -> int:
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("message_id"), int)
            or isinstance(result["message_id"], bool)
        ):
            raise TelegramError(200, "API response is missing its message ID")
        return result["message_id"]

    def send_message(
        self, chat_id: ChatId, html: str, *, disable_notification: bool = False,
        link_preview_url: str | None = None, prefer_large_media: bool = False,
    ) -> int:
        result = self._json_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": html,
                "parse_mode": "HTML",
                "disable_notification": disable_notification,
                "link_preview_options": ({"url": link_preview_url, "prefer_large_media": prefer_large_media}
                                         if link_preview_url is not None else {"is_disabled": True}),
            },
            sending=True,
        )
        return self._message_id(result)

    def send_message_safe(self, chat_id: ChatId, html: str, **kw: Any) -> int:
        try:
            return self.send_message(chat_id, html, **kw)
        except TelegramError as error:
            if error.status != 400 or "can't parse entities" not in error.description.lower():
                raise
        _LOGGER.warning("Telegram rejected HTML entities; retrying the message as plain text")
        result = self._json_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": strip_tags(html),
                "disable_notification": kw.get("disable_notification", False),
                "link_preview_options": ({"url": kw["link_preview_url"], "prefer_large_media": kw.get("prefer_large_media", False)}
                                         if kw.get("link_preview_url") is not None else {"is_disabled": True}),
            },
            sending=True,
        )
        return self._message_id(result)

    def send_document(
        self,
        chat_id: ChatId,
        path: str | os.PathLike[str],
        *,
        caption_html: str | None = None,
        filename: str | None = None,
    ) -> int:
        document = Path(path)
        selected_filename = filename if filename is not None else document.name
        if not selected_filename or any(character in selected_filename for character in "\r\n\x00"):
            raise ValueError("Document filename must be nonempty and contain no line breaks or NUL")
        safe_filename = selected_filename.replace("\\", "\\\\").replace('"', '\\"')
        content_type = mimetypes.guess_type(selected_filename)[0] or "application/octet-stream"
        file_content: bytes | None = None
        try:
            file_content = document.read_bytes()
        except OSError as error:
            description = self._redact(str(error))
        else:
            description = ""
        if file_content is None:
            raise TelegramError(None, description) from None
        return self._upload("sendDocument", "document", chat_id, file_content, safe_filename,
                            content_type, caption_html, parse_html=True)

    def _upload(self, method: str, field: str, chat_id: ChatId, data: bytes, filename: str,
                mime: str, caption: str | None, *, parse_html: bool) -> int:
        boundary = f"econ-digest-{uuid.uuid4().hex}"
        parts: list[bytes] = []
        fields = {"chat_id": str(chat_id)}
        if caption is not None:
            fields["caption"] = caption
            if parse_html:
                fields["parse_mode"] = "HTML"
        for name, value in fields.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode(
                    "utf-8"
                )
            )
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
            f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8")
            + data
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode("ascii"))
        result = self._request(
            method, b"".join(parts), f"multipart/form-data; boundary={boundary}", sending=True
        )
        return self._message_id(result)

    def send_photo(self, chat_id: ChatId, photo: bytes, *, filename: str = "cover.jpg",
                   caption_html: str | None = None) -> int:
        return self._photo(chat_id, photo, filename, caption_html, parse_html=True)

    def _photo(self, chat_id: ChatId, photo: bytes, filename: str, caption: str | None,
               *, parse_html: bool) -> int:
        if not filename or any(character in filename for character in "\r\n\x00"):
            raise ValueError("照片檔名不可為空白或含換行及 NUL 字元")
        safe_filename = filename.replace("\\", "\\\\").replace('"', '\\"')
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return self._upload("sendPhoto", "photo", chat_id, photo, safe_filename, mime,
                            caption, parse_html=parse_html)

    def send_photo_safe(self, chat_id: ChatId, photo: bytes, *, filename: str = "cover.jpg",
                        caption_html: str | None = None) -> int:
        try:
            return self.send_photo(chat_id, photo, filename=filename, caption_html=caption_html)
        except TelegramError as error:
            if error.status != 400 or "can't parse entities" not in error.description.lower():
                raise
        _LOGGER.warning("Telegram 圖說格式解析失敗；改用純文字重試")
        return self._photo(chat_id, photo, filename, strip_tags(caption_html or ""), parse_html=False)


def discover_private_chats(client: TelegramClient) -> list[dict[str, Any]]:
    """Return the newest identity for each private chat seen in pending updates."""
    updates = sorted(client.get_updates(), key=lambda update: update.get("update_id", 0), reverse=True)
    chats: list[dict[str, Any]] = []
    seen: set[int | str] = set()
    for update in updates:
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict) or chat.get("type") != "private":
            continue
        chat_id = chat.get("id")
        if not isinstance(chat_id, (int, str)) or chat_id in seen:
            continue
        seen.add(chat_id)
        chats.append(
            {"chat_id": chat_id, "username": chat.get("username"), "first_name": chat.get("first_name")}
        )
    return chats


def discover_channel(client: TelegramClient) -> ChatId | None:
    updates = sorted(client.get_updates(), key=lambda update: update.get("update_id", 0), reverse=True)
    for update in updates:
        message = update.get("channel_post") or update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            continue
        origin = message.get("forward_origin") or {}
        for chat in (message.get("chat"), origin.get("chat"), message.get("forward_from_chat")):
            if isinstance(chat, dict) and chat.get("type") == "channel" and isinstance(chat.get("id"), (str, int)):
                return chat["id"]
    return None
