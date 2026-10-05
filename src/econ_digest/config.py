"""Validated TOML configuration with file-relative paths and private secrets."""

from __future__ import annotations

import logging
import os
import re
import stat
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

from .taxonomy import CATEGORIES, KINDS, TIER_ORDER

logger = logging.getLogger(__name__)
T = TypeVar("T")
DEFAULT_MODELS = ("gemini-3.8-flash-high", "claude-sonnet-4-6")


class ConfigError(ValueError):
    """A configuration key has an invalid type or value."""


@dataclass(frozen=True)
class PathsConfig:
    data_dir: Path = Path("data")


@dataclass(frozen=True)
class SourceConfig:
    repo: str = "hehonghui/awesome-english-ebooks"
    branch: str = "master"
    folder: str = "01_economist"


@dataclass(frozen=True)
class ModelsConfig:
    classify: tuple[str, ...] = DEFAULT_MODELS
    pair: tuple[str, ...] = DEFAULT_MODELS
    summarize_a: tuple[str, ...] = DEFAULT_MODELS
    summarize_b: tuple[str, ...] = DEFAULT_MODELS
    summarize_c: tuple[str, ...] = DEFAULT_MODELS
    summarize_d: tuple[str, ...] = DEFAULT_MODELS
    summarize_e: tuple[str, ...] = DEFAULT_MODELS
    brief: tuple[str, ...] = DEFAULT_MODELS
    english: tuple[str, ...] = DEFAULT_MODELS


@dataclass(frozen=True)
class LLMConfig:
    backend: str = "gwg"
    gwg_bin: str = "gwg"
    max_parallel: int = 2
    call_timeout_seconds: int = 300
    no_account_wait_seconds: int = 900
    models: ModelsConfig = field(default_factory=ModelsConfig)


@dataclass(frozen=True)
class TiersConfig:
    cover_companion_min: str = "B"
    leader_companion_min: str = "C"
    taiwan: dict[str, str] = field(default_factory=lambda: {"1": "A", "2": "B", "3": "C"})
    category: dict[str, str] = field(default_factory=lambda: {
        "intl.us": "C", "intl.china": "C", "intl.asia": "D", "intl.europe": "D",
        "finance": "D", "tech": "D", "intl.other": "E", "science": "E", "culture": "E",
    })
    min_tier_by_kind: dict[str, str] = field(default_factory=lambda: {"briefing": "C"})
    force_tier_by_kind: dict[str, str] = field(default_factory=lambda: {"letters": "E", "obituary": "E"})


@dataclass(frozen=True)
class EnglishConfig:
    level: str = "全民英檢中級（多益約 550–780，CEFR B1）"
    min_words: int = 600
    max_words: int = 1300
    vocab_count: int = 14
    phrase_count: int = 7


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = True
    send_report_file: bool = False
    message_delay_seconds: float = 1.1
    delivery: str = "telegraph"


@dataclass(frozen=True)
class TelegraphConfig:
    author_name: str = "經濟學人導讀"
    author_url: str = ""
    page_limit_bytes: int = 60000


@dataclass(frozen=True)
class SecretsConfig:
    telegram_bot_token: str | None = field(default=None, repr=False)
    telegram_chat_id: str | None = field(default=None, repr=False)
    github_token: str | None = field(default=None, repr=False)
    telegraph_access_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Config:
    paths: PathsConfig = field(default_factory=PathsConfig)
    source: SourceConfig = field(default_factory=SourceConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tiers: TiersConfig = field(default_factory=TiersConfig)
    english: EnglishConfig = field(default_factory=EnglishConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    telegraph: TelegraphConfig = field(default_factory=TelegraphConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig, repr=False)


def _fail(key: str, expected: str) -> None:
    raise ConfigError(f"{key}: {expected}")


def _convert(value: Any, annotation: Any, key: str, base_dir: Path) -> Any:
    if is_dataclass(annotation):
        if not isinstance(value, dict):
            _fail(key, "必須是 TOML 表格")
        return _build(annotation, value, key, base_dir)
    if annotation is Path:
        if not isinstance(value, str) or not value.strip():
            _fail(key, "必須是非空路徑字串")
        path = Path(value).expanduser()
        return (base_dir / path).resolve()
    if annotation is str:
        if not isinstance(value, str) or (not value.strip() and key != "telegraph.author_url"):
            _fail(key, "必須是非空字串")
        return value
    if annotation is bool:
        if type(value) is not bool:
            _fail(key, "必須是布林值")
        return value
    if annotation is int:
        if type(value) is not int:
            _fail(key, "必須是整數")
        return value
    if annotation is float:
        if type(value) not in (int, float):
            _fail(key, "必須是數字")
        return float(value)
    origin = get_origin(annotation)
    if origin is tuple:
        if not isinstance(value, list) or not value:
            _fail(key, "必須是非空字串陣列")
        return tuple(_convert(item, str, f"{key}[{i}]", base_dir) for i, item in enumerate(value))
    if origin is dict:
        if not isinstance(value, dict):
            _fail(key, "必須是 TOML 表格")
        key_type, value_type = get_args(annotation)
        return {
            _convert(k, key_type, key, base_dir): _convert(v, value_type, f"{key}.{k}", base_dir)
            for k, v in value.items()
        }
    _fail(key, "不支援的設定類型")


def _build(cls: type[T], data: dict[str, Any], prefix: str, base_dir: Path) -> T:
    defaults = cls()
    hints = get_type_hints(cls)
    names = {f.name for f in fields(cls)} - {"secrets"}
    for name in data.keys() - names:
        logger.warning("未知的設定鍵：%s", f"{prefix}.{name}".lstrip("."))
    values: dict[str, Any] = {}
    for name in names:
        key = f"{prefix}.{name}".lstrip(".")
        if name in data:
            value = data[name]
            if prefix == "tiers" and isinstance(value, dict):
                allowed = {
                    "taiwan": {"1", "2", "3"}, "category": set(CATEGORIES),
                    "min_tier_by_kind": set(KINDS), "force_tier_by_kind": set(KINDS),
                }[name]
                for unknown in value.keys() - allowed:
                    logger.warning("未知的設定鍵：%s.%s", key, unknown)
                value = {k: v for k, v in value.items() if k in allowed}
                if name in ("taiwan", "category"):
                    value = {**getattr(defaults, name), **value}
            values[name] = _convert(value, hints[name], key, base_dir)
            if key == "llm.gwg_bin" and ("/" in values[name] or values[name].startswith("~")):
                values[name] = str((base_dir / Path(values[name]).expanduser()).resolve())
        elif hints[name] is Path:
            values[name] = (base_dir / getattr(defaults, name)).resolve()
        elif is_dataclass(hints[name]):
            values[name] = _build(hints[name], {}, key, base_dir)
    return cls(**values)


def _validate(config: Config) -> None:
    for name in ("cover_companion_min", "leader_companion_min"):
        if getattr(config.tiers, name) not in TIER_ORDER:
            _fail(f"tiers.{name}", "必須是 A、B、C、D 或 E")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", config.source.repo):
        _fail("source.repo", "必須是 owner/repo 格式")
    if config.source.folder.startswith("/") or ".." in config.source.folder.split("/"):
        _fail("source.folder", "必須是儲存庫內的相對路徑")
    if config.llm.backend != "gwg":
        _fail("llm.backend", "目前僅支援 gwg")
    for key in ("max_parallel", "call_timeout_seconds", "no_account_wait_seconds"):
        if getattr(config.llm, key) <= 0:
            _fail(f"llm.{key}", "必須大於零")
    for key in ("min_words", "max_words", "vocab_count", "phrase_count"):
        if getattr(config.english, key) <= 0:
            _fail(f"english.{key}", "必須大於零")
    if config.english.max_words < config.english.min_words:
        _fail("english.max_words", "必須大於或等於 english.min_words")
    if not 0 <= config.telegram.message_delay_seconds < float("inf"):
        _fail("telegram.message_delay_seconds", "必須是有限的非負數")
    if config.telegram.delivery not in ("telegraph", "messages"):
        _fail("telegram.delivery", "必須是 telegraph 或 messages")
    if not 1 <= config.telegraph.page_limit_bytes <= 64000:
        _fail("telegraph.page_limit_bytes", "必須介於 1 與 64000 之間")
    if len(config.telegraph.author_name) > 128:
        _fail("telegraph.author_name", "最多 128 個字元")
    if len(config.telegraph.author_url) > 512:
        _fail("telegraph.author_url", "最多 512 個字元")
    allowed = {
        "taiwan": {"1", "2", "3"}, "category": set(CATEGORIES),
        "min_tier_by_kind": set(KINDS), "force_tier_by_kind": set(KINDS),
    }
    for name, keys in allowed.items():
        for key, tier in getattr(config.tiers, name).items():
            if key not in keys:
                logger.warning("未知的設定鍵：tiers.%s.%s", name, key)
            if tier not in TIER_ORDER:
                _fail(f"tiers.{name}.{key}", "必須是 A、B、C、D 或 E")


def _load_secrets() -> SecretsConfig:
    values = dict(os.environ)
    env_path = Path(values.get("ECON_DIGEST_ENV_FILE", "~/.config/econ-digest/env")).expanduser()
    names = {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GITHUB_TOKEN", "TELEGRAPH_ACCESS_TOKEN"}
    try:
        mode = env_path.stat().st_mode
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ConfigError("ECON_DIGEST_ENV_FILE: 無法讀取密鑰檔") from exc
    else:
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            logger.warning("密鑰檔可供群組或其他使用者讀取：%s", env_path)
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ConfigError("ECON_DIGEST_ENV_FILE: 無法讀取密鑰檔") from exc
        for number, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key = key.strip()
            if not separator:
                logger.warning("密鑰檔第 %d 行格式錯誤（應為 KEY=VALUE）", number)
                continue
            if key in names:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values.setdefault(key, value)
    return SecretsConfig(
        telegram_bot_token=values.get("TELEGRAM_BOT_TOKEN") or None,
        telegram_chat_id=values.get("TELEGRAM_CHAT_ID") or None,
        github_token=values.get("GITHUB_TOKEN") or None,
        telegraph_access_token=values.get("TELEGRAPH_ACCESS_TOKEN") or None,
    )


def load_config(path: str | Path | None = None) -> Config:
    selected = path if path is not None else os.environ.get("ECON_DIGEST_CONFIG")
    required = selected is not None
    config_path = Path(selected or "config.toml").expanduser().resolve()
    base_dir = config_path.parent if required or config_path.exists() else Path.cwd()
    data: dict[str, Any] = {}
    try:
        with config_path.open("rb") as stream:
            data = tomllib.load(stream)
    except FileNotFoundError as exc:
        if required:
            raise ConfigError(f"config: 找不到設定檔 {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        # TOML parser messages may quote a secret accidentally placed in this file.
        raise ConfigError(f"config: TOML 格式錯誤（{config_path}）") from exc
    except OSError as exc:
        raise ConfigError(f"config: 無法讀取設定檔 {config_path}") from exc
    config = _build(Config, data, "", base_dir)
    _validate(config)
    return Config(
        paths=config.paths, source=config.source, llm=config.llm, tiers=config.tiers,
        english=config.english, telegram=config.telegram, telegraph=config.telegraph,
        secrets=_load_secrets(),
    )
