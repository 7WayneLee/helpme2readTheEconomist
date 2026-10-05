"""stderr and rotating-file logging with credential redaction."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Config, SecretsConfig


def redact(text: str, secrets: SecretsConfig | None = None) -> str:
    if secrets:
        for value in (secrets.telegram_bot_token, secrets.telegram_chat_id, secrets.github_token,
                      secrets.telegraph_access_token, secrets.telegram_channel_id):
            if value:
                text = text.replace(value, "[已隱藏]")
    return re.sub(r"(https?://api\.telegram\.org/bot)[^/\s]+", r"\1[已隱藏]", text)


class _RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: SecretsConfig | None = None) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.secrets = secrets

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), self.secrets)


def setup_logging(
    data_dir: str | Path, verbose: bool = False, secrets: SecretsConfig | None = None,
) -> None:
    directory = Path(data_dir) / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    formatter = _RedactingFormatter(secrets)
    stream = logging.StreamHandler()
    file = RotatingFileHandler(directory / "econ-digest.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    for handler in (stream, file):
        handler.setFormatter(formatter)
        setattr(handler, "_econ_digest_handler", True)
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_econ_digest_handler", False):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(stream)
    root.addHandler(file)


def configure_logging(config: Config, verbose: bool = False) -> None:
    setup_logging(config.paths.data_dir, verbose, config.secrets)
