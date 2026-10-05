"""Shared generation policy for production and deterministic clients."""

import logging
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .api import LLMError, LLMResult
from .jsonutil import extract_json_object

logger = logging.getLogger(__name__)
MAX_PROMPT_BYTES = 100_000


@dataclass
class Attempt:
    output: dict[str, Any] | str | None = None
    kind: str = "success"
    error: str = ""
    total_tokens: int = 0
    duration_seconds: float = 0.0


def classify_error(text: str, returncode: int | None = None) -> str:
    if returncode == 75:
        return "no_account"
    lowered = text.lower()
    if "location" in lowered and ("not supported" in lowered or "unsupported" in lowered):
        return "location"
    if any(term in lowered for term in ("resource_exhausted", "quota", "429", "rate limit")):
        return "quota"
    if any(term in lowered for term in ("unauthenticated", "unauthorized", "authentication", "sign-in", "sign in", "login", "credential", "401", "403")):
        return "auth"
    if any(term in lowered for term in ("timeout", "timed out", "deadline_exceeded")):
        return "timeout"
    return "error"


class JSONClient:
    def __init__(self, *, call_timeout: float = 300, no_account_wait: float = 900,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not math.isfinite(call_timeout) or call_timeout <= 0:
            raise ValueError("call_timeout must be positive and finite")
        if not math.isfinite(no_account_wait) or no_account_wait < 0:
            raise ValueError("no_account_wait must be nonnegative and finite")
        self.call_timeout = call_timeout
        self.no_account_wait = no_account_wait
        self.sleep = sleep

    def _invoke(self, prompt: str, model: str, stage: str, timeout: float) -> Attempt:
        raise NotImplementedError

    def generate_json(
        self, prompt: str, *, models: Sequence[str], stage: str = "",
        validate: Callable[[dict[str, Any]], None] | None = None,
        timeout: float | None = None,
    ) -> LLMResult:
        if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise ValueError("Prompt exceeds 100,000 UTF-8 bytes; split the input into smaller batches")
        if not models:
            raise ValueError("At least one model is required")
        effective_timeout = self.call_timeout if timeout is None else timeout
        if not math.isfinite(effective_timeout) or effective_timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        attempts: list[dict[str, Any]] = []
        wait_remaining = self.no_account_wait
        backoff = 30.0
        for model in models:
            current_prompt = prompt
            repaired = False
            retried = False
            while True:
                logger.debug("LLM stage=%s model=%s prompt=%s", stage, model,
                             current_prompt[:200].replace("\r", " ").replace("\n", " "))
                attempt = self._invoke(current_prompt, model, stage, effective_timeout)
                data: dict[str, Any] | None = None
                if attempt.kind == "success":
                    try:
                        if isinstance(attempt.output, dict):
                            data = attempt.output
                        elif isinstance(attempt.output, str):
                            data = extract_json_object(attempt.output)
                        else:
                            raise ValueError("Model output must be a JSON object or text containing one")
                        if validate is not None:
                            validate(data)
                    except ValueError as exc:
                        attempt.kind = "invalid_output"
                        attempt.error = str(exc)
                record = {
                    "model": model, "outcome": attempt.kind, "error": attempt.error,
                    "total_tokens": attempt.total_tokens, "duration_seconds": attempt.duration_seconds,
                }
                attempts.append(record)
                logger.info("LLM stage=%s model=%s outcome=%s tokens=%d seconds=%.3f", stage, model,
                            attempt.kind, attempt.total_tokens, attempt.duration_seconds)
                if attempt.kind == "success":
                    assert data is not None
                    return LLMResult(data, model, attempt.total_tokens, attempt.duration_seconds, attempts)
                if attempt.kind == "no_account":
                    if wait_remaining <= 0:
                        raise LLMError(attempt.error or "No free gwg account before wait budget expired",
                                       kind="no_account", attempts=attempts)
                    delay = min(backoff, wait_remaining)
                    self.sleep(delay)
                    wait_remaining -= delay
                    backoff *= 2
                    continue
                if attempt.kind == "invalid_output" and not repaired:
                    repaired = True
                    current_prompt = prompt + (
                        f"\n\n上一次的輸出無法使用（錯誤：{attempt.error[:500]}）。"
                        "請只輸出一個符合要求格式的 JSON 物件，不要有任何其他文字。"
                    )
                    # The input cap leaves room below Linux's argv limit for this bounded repair.
                    continue
                elif attempt.kind in ("timeout", "error") and not retried:
                    retried = True
                    continue
                break
        last = attempts[-1]
        raise LLMError(last["error"] or "All models failed", kind=last["outcome"], attempts=attempts)
