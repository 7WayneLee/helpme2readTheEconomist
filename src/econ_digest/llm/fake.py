"""Deterministic in-process client for application tests."""

import time
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Lock
from typing import Any

from ._retry import Attempt, JSONClient, classify_error
from .api import LLMError


class FakeLLMClient(JSONClient):
    def __init__(self, responder: Callable[[str, str, str], dict[str, Any] | str | Exception], *,
                 no_account_wait: float = 900, sleep: Callable[[float], None] = time.sleep) -> None:
        super().__init__(no_account_wait=no_account_wait, sleep=sleep)
        self.responder = responder
        self.calls: list[tuple[str, str, str]] = []
        self._calls_lock = Lock()

    def _invoke(self, prompt: str, model: str, stage: str, timeout: float,
                extra_read_dirs: Sequence[str | Path] = ()) -> Attempt:
        with self._calls_lock:
            self.calls.append((prompt, model, stage))
        started = time.monotonic()
        try:
            output = self.responder(prompt, model, stage)
            if isinstance(output, Exception):
                raise output
        except Exception as exc:
            if isinstance(exc, LLMError):
                kind = exc.kind
            elif isinstance(exc, ValueError):
                kind = "invalid_output"
            elif isinstance(exc, TimeoutError):
                kind = "timeout"
            else:
                kind = classify_error(str(exc))
            return Attempt(kind=kind, error=str(exc), duration_seconds=time.monotonic() - started)
        return Attempt(output=output, duration_seconds=time.monotonic() - started)
