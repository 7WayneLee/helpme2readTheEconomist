"""Character conversion, an explicit glossary, and Chinese quotation marks."""

import copy
import logging
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)
DEFAULT_SKIP_KEYS = frozenset({
    "en", "example_en", "sentence_en", "word", "phrase", "pos", "article_id", "model",
    "tier", "category", "companion_id", "cefr",
})
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]+")
_QUOTES = (re.compile(r'“([^”]*)”'), re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"'))
_GLOSSARY = tuple(
    line.split("\t", 2)[:2]
    for line in Path(__file__).with_name("glossary.tsv").read_text(encoding="utf-8").splitlines()
    if line and not line.startswith("#")
)
_REPLACEMENTS = dict(_GLOSSARY)
# Preferred forms also participate so, for example, 演算法 does not become 演演算法.
_TERMS = re.compile("|".join(re.escape(term) for term in sorted(set(_REPLACEMENTS) | set(_REPLACEMENTS.values()), key=lambda term: (-len(term), term))))
_warning_lock = Lock()
_warned_opencc = False


def _warn_opencc(message: str) -> None:
    global _warned_opencc
    with _warning_lock:
        if not _warned_opencc:
            logger.warning("OpenCC conversion skipped: %s", message)
            _warned_opencc = True


@lru_cache(maxsize=8192)
def _is_simplified(character: str) -> bool:
    if not _CJK.fullmatch(character):
        return False
    try:
        character.encode("cp950")
    except UnicodeEncodeError:
        return True
    return False


def _has_simplified(text: str) -> bool:
    return any(_is_simplified(character) for character in text)


def _convert_text(text: str, executable: str) -> str | None:
    try:
        result = subprocess.run([executable, "-c", "s2tw"], input=text, capture_output=True,
                                text=True, encoding="utf-8", check=True, timeout=30)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        _warn_opencc(type(exc).__name__)
        return None
    return result.stdout


def _convert_batch(strings: list[str]) -> list[str]:
    if not strings:
        return []
    executable = shutil.which("opencc")
    if executable is None:
        _warn_opencc("opencc executable was not found")
        return list(strings)
    separator = "\nECON_DIGEST_SEPARATOR_" + uuid.uuid4().hex + "\n"
    while any(separator in text for text in strings):
        separator = "\nECON_DIGEST_SEPARATOR_" + uuid.uuid4().hex + "\n"
    output = _convert_text(separator.join(strings), executable)
    if output is None:
        return list(strings)
    converted = output.split(separator)
    if len(converted) != len(strings):
        _warn_opencc("batch output count did not match input; original runs preserved")
        return list(strings)
    return [text.replace("臺", "台") for text in converted]


def _finish(text: str) -> str:
    text = _TERMS.sub(lambda match: _REPLACEMENTS.get(match.group(), match.group()), text)

    def quote(match: re.Match[str]) -> str:
        span = match.group(1)
        return "「" + span + "」" if _CJK.search(span) else match.group()

    for pattern in _QUOTES:
        text = pattern.sub(quote, text)
    return text


def normalize_zh_tw(text: str) -> str:
    return normalize_tree(text)


def _map_strings(value: Any, transform: Callable[[str], str], skip_keys: frozenset[str]) -> Any:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, dict):
        return {copy.deepcopy(key): copy.deepcopy(item) if key in skip_keys else _map_strings(item, transform, skip_keys)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_map_strings(item, transform, skip_keys) for item in value]
    if isinstance(value, tuple):
        return tuple(_map_strings(item, transform, skip_keys) for item in value)
    return copy.deepcopy(value)


def normalize_tree(value: Any, skip_keys: frozenset[str] = DEFAULT_SKIP_KEYS) -> Any:
    runs: list[str] = []

    def collect(text: str) -> str:
        runs.extend(match.group() for match in _CJK.finditer(text) if _has_simplified(match.group()))
        return text

    tree = _map_strings(value, collect, skip_keys)
    converted = iter(_convert_batch(runs))

    def replace(text: str) -> str:
        return _finish(_CJK.sub(lambda match: next(converted) if _has_simplified(match.group()) else match.group(), text))

    return _map_strings(tree, replace, skip_keys)


def lint_zh_tw(text: str) -> list[str]:
    remaining = {match.group() for match in _TERMS.finditer(text) if match.group() in _REPLACEMENTS}
    warnings = [f"建議將「{source}」改為「{target}」。" for source, target in _GLOSSARY if source in remaining]
    characters = sorted(character for character in set(text) if _is_simplified(character))
    if characters:
        warnings.append("疑似殘留簡體字：" + "、".join(characters) + "。")
    return warnings
