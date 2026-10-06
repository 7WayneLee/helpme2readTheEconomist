"""Private token storage; environment rotation supersedes an older cached token."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

from ..config import Config
from ..models import save_json
from ..state import StateError


def timestamp(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("時間戳記必須包含時區。")
    return stamp.astimezone(timezone.utc)


@dataclass(frozen=True)
class Token:
    access_token: str = field(repr=False)
    user_id: str = field(repr=False)
    issued_at: datetime
    expires_at: datetime
    source_hash: str = field(repr=False)
    age_estimated: bool = False

    def age_days(self, now: datetime) -> float:
        return max(0, (now - self.issued_at).total_seconds() / 86400)


def token_path(config: Config) -> Path:
    return config.paths.data_dir / "social" / "threads_token.json"


def load_token(config: Config, now: datetime) -> Token | None:
    cache = None
    try:
        saved = json.loads(token_path(config).read_text(encoding="utf-8"))
        cache = Token(saved["access_token"], saved["user_id"], timestamp(saved["issued_at"]),
                      timestamp(saved["expires_at"]), saved["source_hash"], saved.get("age_estimated", False))
        if (not cache.access_token or not isinstance(cache.access_token, str)
                or not isinstance(cache.user_id, str) or not isinstance(cache.source_hash, str)
                or cache.issued_at >= cache.expires_at):
            raise ValueError
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError):
        raise StateError("Threads 權杖快取無法讀取；請保留密鑰檔並重新設定。") from None
    secret = config.secrets
    if bool(secret.threads_access_token) != bool(secret.threads_user_id):
        raise StateError("THREADS_ACCESS_TOKEN 與 THREADS_USER_ID 必須一起設定。")
    if not secret.threads_access_token or not secret.threads_user_id:
        return cache
    source_hash = hashlib.sha256((secret.threads_access_token + "\0" +
                                 (secret.threads_token_issued_at or "")).encode()).hexdigest()
    if cache and cache.source_hash == source_hash and cache.user_id == secret.threads_user_id:
        return cache
    estimated = not secret.threads_token_issued_at
    try:
        if secret.threads_token_issued_at:
            issued = timestamp(secret.threads_token_issued_at)
        else:
            env_file = Path(os.environ.get("ECON_DIGEST_ENV_FILE", "~/.config/econ-digest/env")).expanduser()
            issued = datetime.fromtimestamp(env_file.stat().st_mtime, timezone.utc) if env_file.exists() else now
    except (ValueError, OSError):
        raise StateError("THREADS_TOKEN_ISSUED_AT 必須是含時區的 ISO 日期時間。") from None
    if issued > now + timedelta(minutes=5):
        raise StateError("THREADS_TOKEN_ISSUED_AT 不能是未來時間。")
    # If a cache was refreshed after this source token was issued, prefer it.
    if cache and cache.user_id == secret.threads_user_id and cache.issued_at > issued:
        return cache
    return Token(secret.threads_access_token, secret.threads_user_id, issued,
                 issued + timedelta(days=60), source_hash, estimated)


def store_token(config: Config, token: Token) -> None:
    path = token_path(config)
    save_json(path, {"access_token": token.access_token, "user_id": token.user_id,
                     "issued_at": token.issued_at.isoformat(), "expires_at": token.expires_at.isoformat(),
                     "source_hash": token.source_hash, "age_estimated": token.age_estimated})
    path.chmod(0o600)
