"""Validated, normalised successes only; failed units remain retryable."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from ..llm import LLMClient, LLMError
from ..models import LLMCallStat, save_json
from ..zhtw import DEFAULT_SKIP_KEYS, normalize_tree
from .prompts import Unit

SKIP_KEYS = DEFAULT_SKIP_KEYS | {"id", "question", "section", "kind", "title", "source_url", "issue_date"}


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
        if not isinstance(envelope, dict) or envelope.get("key") != unit.cache_key:
            return None
        data = envelope.get("data")
        model = envelope.get("model")
        if not isinstance(data, dict) or not isinstance(model, str) or model not in unit.models:
            return None
        unit.validate(data)
        return UnitResult(unit, normalize_tree(data, skip_keys=SKIP_KEYS), model)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        return None


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
            data = normalize_tree(result.data, skip_keys=SKIP_KEYS)
            save_json(cache_path(self.workdir, unit), {"key": unit.cache_key, "data": data, "model": result.model})
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
