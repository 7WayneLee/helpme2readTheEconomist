"""Describe only the inline illustrations displayed in private deep analyses."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import replace
import hashlib
from typing import Any
from zipfile import BadZipFile

from ..config import Config
from ..fetch import issue_directory
from ..images import (ImageBlob, IssueImages, figure_image_path, inline_images_allowed,
                      load_issue_images)
from ..llm import run_parallel
from ..models import ArticleSummary, Classification, Issue
from ..zhtw import normalize_zh_tw
from .cache import UnitRunner
from .prompts import Unit, make_unit, prompt_json, split_units

FIGURE_KINDS = frozenset({"chart", "map", "photo", "illustration"})
FIGURE_WARNING = "插圖說明產生失敗，圖片保留但無說明。"


def validate_figures(data: dict[str, Any], image_names: Sequence[str]) -> None:
    """Require an unambiguous response for every requested image.

    Content is checked separately by figure_note so one bad description cannot
    discard usable captions for the other images in the same call.
    """
    items = data.get("figures")
    if (not isinstance(items, list) or any(not isinstance(item, dict)
                                          or not isinstance(item.get("image"), str) for item in items)):
        raise ValueError("figures must be a list of objects with image names")
    if Counter(item["image"] for item in items) != Counter(image_names):
        raise ValueError("Every requested image must occur exactly once, with no extra images")


def figure_note(item: dict[str, Any]) -> dict[str, str]:
    """Validate and normalise one caption; the caller omits invalid items."""
    kind = item.get("kind")
    if not isinstance(kind, str) or kind not in FIGURE_KINDS:
        raise ValueError("kind must be chart, map, photo or illustration")
    description = item.get("description_zh")
    if not isinstance(description, str) or "社論" in description:
        raise ValueError("description_zh must be text without the prohibited term")
    description = normalize_zh_tw(description.strip())
    minimum, maximum = (20, 160) if kind in {"chart", "map"} else (8, 60)
    if not minimum <= len(description) <= maximum:
        raise ValueError(f"{kind} description_zh requires {minimum}–{maximum} characters")
    return {"kind": kind, "description_zh": description}


def figure_units(issue: Issue, classifications: dict[str, Classification],
                 summaries: dict[str, ArticleSummary], focus_ids: Collection[str], config: Config,
                 *, images: IssueImages | None = None, extract: bool = True) -> list[Unit]:
    directory = issue_directory(config, issue.issue_date)
    if images is None:
        epub = directory / f"TheEconomist.{issue.issue_date}.epub"
        if not epub.exists():
            return []
        images = load_issue_images(epub)
    units: list[Unit] = []
    for article in issue.articles:
        classification = classifications.get(article.id)
        summary = summaries.get(article.id)
        if (classification is None or summary is None or not summary.structure
                or not inline_images_allowed(summary.tier, classification.taiwan_level,
                                             article.id, focus_ids)):
            continue
        selected = images.by_article.get(article.id)
        if not selected or not selected.inline:
            continue
        blobs = [positioned.image for positioned in selected.inline]
        paths = {blob.name: figure_image_path(directory / "figures", blob, extract=extract) for blob in blobs}

        def build(batch: list[ImageBlob]) -> Unit:
            names = tuple(blob.name for blob in batch)
            unit = make_unit("figures", issue.issue_date, [article.id], config.llm.models.figures,
                             lambda data: validate_figures(data, names),
                             images=prompt_json([{"image": blob.name, "path": str(paths[blob.name])}
                                                 for blob in batch]))
            return replace(unit,
                           extra_read_dirs=tuple(dict.fromkeys(paths[blob.name].parent for blob in batch)),
                           image_hashes=tuple((blob.name, hashlib.sha256(blob.data).hexdigest()) for blob in batch))

        units.extend(split_units(blobs, build, max_items=4, max_bytes=90_000))
    return units


def describe_figures(issue: Issue, classifications: dict[str, Classification],
                     summaries: dict[str, ArticleSummary], focus_ids: Collection[str], config: Config,
                     runner: UnitRunner, warnings: list[str]) -> dict[str, dict]:
    notes: dict[str, dict] = {}
    failed = False
    try:
        units = figure_units(issue, classifications, summaries, focus_ids, config)
    except (OSError, ValueError, BadZipFile):
        warnings.append(FIGURE_WARNING)
        return notes
    for result in run_parallel(runner.run, units, config.llm.max_parallel):
        if isinstance(result, BaseException):
            raise result
        if result.data is None:
            failed = True
            continue
        for item in result.data["figures"]:
            try:
                notes[item["image"]] = figure_note(item)
            except ValueError:
                failed = True
    if failed:
        warnings.append(FIGURE_WARNING)
    return notes
