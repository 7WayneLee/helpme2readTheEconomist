"""Cache validated raw successes so normaliser changes need no new LLM calls."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from ..llm import LLMClient, LLMError
from ..models import LLMCallStat, save_json
from ..zhtw import DEFAULT_SKIP_KEYS
from .prompts import Unit

SKIP_KEYS = DEFAULT_SKIP_KEYS | {"id", "focus_ids", "question", "section", "kind", "title", "source_url", "issue_date",
                                "sources", "url", "evidence_url", "basis", "date"}
CACHE_FORMAT_VERSION = 2


@dataclass
class UnitResult:
    unit: Unit
    data: dict[str, Any] | None
    model: str = ""
    error_kind: str | None = None


def cache_path(workdir: Path, unit: Unit) -> Path:
    return workdir / f"{unit.stage}-{unit.cache_key}.json"


def read_cache(workdir: Path, unit: Unit) -> UnitResult | None:
    try:
        envelope = json.loads(cache_path(workdir, unit).read_text(encoding="utf-8"))
        if (not isinstance(envelope, dict) or envelope.get("key") != unit.cache_key
                or envelope.get("format_version") != CACHE_FORMAT_VERSION):
            return None
        data = envelope.get("data")
        model = envelope.get("model")
        if not isinstance(data, dict) or not isinstance(model, str) or model not in unit.models:
            return None
        unit.validate(data)
        fallback_error = envelope.get("fallback_error_kind")
        if fallback_error is not None and (unit.stage != "focus" or not isinstance(fallback_error, str)):
            return None
        return UnitResult(unit, data, model, fallback_error)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        return None


def cache_focus_fallback(workdir: Path, result: UnitResult, data: dict[str, Any]) -> None:
    """Keep a recovered focus decision and its warning on a warm rerun."""
    result.unit.validate(data)
    save_json(cache_path(workdir, result.unit), {"format_version": CACHE_FORMAT_VERSION,
                                              "key": result.unit.cache_key, "data": data,
                                              "model": result.model, "fallback_error_kind": result.error_kind})


class UnitRunner:
    def __init__(self, llm: LLMClient, workdir: Path, progress: Callable[[str], None] | None = None) -> None:
        self.llm = llm
        self.workdir = workdir
        self.progress = progress
        self.stats: list[LLMCallStat] = []
        self.total_units = 0
        self.failed_units = 0
        self._lock = Lock()
        workdir.mkdir(parents=True, exist_ok=True)

    def run(self, unit: Unit) -> UnitResult:
        cached = read_cache(self.workdir, unit)
        with self._lock:
            self.total_units += 1
            if self.progress:
                self.progress(f"{unit.stage}：{len(unit.article_ids)} 篇" + ("（快取）" if cached else ""))
        if cached:
            return cached
        try:
            result = self.llm.generate_json(unit.prompt, models=unit.models, stage=unit.stage, validate=unit.validate)
            # Also enforce the contract for third-party implementations of LLMClient.
            unit.validate(result.data)
            data = result.data
            save_json(cache_path(self.workdir, unit), {"format_version": CACHE_FORMAT_VERSION,
                                                     "key": unit.cache_key, "data": data, "model": result.model})
        except (LLMError, ValueError) as exc:
            attempts = exc.attempts if isinstance(exc, LLMError) else []
            model = str(attempts[-1].get("model", unit.models[-1])) if attempts else unit.models[-1]
            stat = LLMCallStat(unit.stage, model, False, sum(int(item.get("total_tokens", 0)) for item in attempts),
                               sum(float(item.get("duration_seconds", 0)) for item in attempts))
            with self._lock:
                self.failed_units += 1
                self.stats.append(stat)
            return UnitResult(unit, None, model, exc.kind if isinstance(exc, LLMError) else "invalid_output")
        attempts = result.attempts
        stat = LLMCallStat(unit.stage, result.model, True,
                           sum(int(item.get("total_tokens", 0)) for item in attempts) if attempts else result.total_tokens,
                           sum(float(item.get("duration_seconds", 0)) for item in attempts) if attempts else result.duration_seconds)
        with self._lock:
            self.stats.append(stat)
        return UnitResult(unit, data, result.model)
