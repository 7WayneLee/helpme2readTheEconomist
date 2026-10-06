"""Render compact prompts and split calls by their actual UTF-8 size."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, TypeVar

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
T = TypeVar("T")


@dataclass(frozen=True)
class Unit:
    stage: str
    article_ids: tuple[str, ...]
    prompt: str
    models: tuple[str, ...]
    validate: Callable[[dict[str, Any]], None]
    tier: str = ""
    prompt_hash: str = ""
    extra_read_dirs: tuple[Path, ...] = ()
    image_hashes: tuple[tuple[str, str], ...] = ()
    cache_prompt: str | None = None

    @property
    def prompt_bytes(self) -> int:
        return len(self.prompt.encode("utf-8"))

    @property
    def cache_key(self) -> str:
        identity = [self.stage, sorted(self.article_ids), self.tier, self.prompt_hash,
                    list(self.models), self.prompt if self.cache_prompt is None else self.cache_prompt]
        # Keep every existing text-stage key unchanged.
        if self.image_hashes:
            identity.append(self.image_hashes)
        return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def prompt_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def render_prompt(name: str, issue_date: str, **values: Any) -> tuple[str, str]:
    style = (PROMPT_DIR / "_style.md").read_text(encoding="utf-8")
    if name == "edit":
        # Keep core rules and blacklist substitutions, omit table explanations
        # and the long title examples: the full preamble exceeds 9 KB itself.
        blacklist = []
        for row in style.split("\n## 四、", 1)[0].splitlines():
            if row.startswith("| **"):
                columns = row.split("|")
                blacklist.append(columns[1].strip() + " → " + columns[3].strip())
        style = style.split("\n## 三、", 1)[0] + "\n翻譯腔替換：\n" + "\n".join(blacklist)
    common = (PROMPT_DIR / "_common.md").read_text(encoding="utf-8")
    if name == "figures":
        # Vision needs local image access; all text prompts retain their exact
        # source and hash, including the shared no-tools instruction.
        common = common.replace("不要使用任何工具，直接回答。",
                                "只使用讀檔或讀圖工具開啟指定的圖片，不要使用其他工具。")
        common = common.replace("較少見者首次寫中文譯名（English）。",
                                "名稱有通用中文譯名時只用中文，沒有通用譯名時才保留英文。")
    source = style + "\n" + common + "\n" + (
        PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode()).hexdigest()
    return Template(source).substitute(issue_date=issue_date, **values), digest


def make_unit(name: str, issue_date: str, article_ids: Sequence[str], models: Sequence[str],
              validate: Callable[[dict[str, Any]], None], *, tier: str = "",
              stage: str | None = None, **values: Any) -> Unit:
    prompt, digest = render_prompt(name, issue_date, **values)
    return Unit(stage or name, tuple(article_ids), prompt, tuple(models), validate, tier, digest)


def split_units(items: Sequence[T], build: Callable[[list[T]], Unit], *,
                max_items: int, max_bytes: int) -> list[Unit]:
    units: list[Unit] = []
    batch: list[T] = []
    for item in items:
        candidate = batch + [item]
        if len(candidate) > max_items or build(candidate).prompt_bytes > max_bytes:
            if batch:
                units.append(build(batch))
            batch = [item]
            if build(batch).prompt_bytes > max_bytes:
                raise ValueError(f"{build(batch).stage}: article exceeds {max_bytes:,} prompt bytes")
        else:
            batch = candidate
    if batch:
        units.append(build(batch))
    return units


def numbered_text(paragraphs: Sequence[str]) -> str:
    return "\n".join(f"[{index}] {paragraph}" for index, paragraph in enumerate(paragraphs, 1))


def first_words(paragraphs: Sequence[str], count: int) -> str:
    return " ".join(" ".join(paragraphs).split()[:count])
