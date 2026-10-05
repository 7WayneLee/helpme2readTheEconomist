"""Public result types and the client contract."""

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar


class LLMError(Exception):
    def __init__(self, message: str, *, kind: str = "error", attempts: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.attempts = [] if attempts is None else list(attempts)


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    total_tokens: int
    duration_seconds: float
    attempts: list[dict[str, Any]]


class LLMClient(Protocol):
    def generate_json(
        self, prompt: str, *, models: Sequence[str], stage: str = "",
        validate: Callable[[dict[str, Any]], None] | None = None,
        timeout: float | None = None,
    ) -> LLMResult: ...


T = TypeVar("T")
R = TypeVar("R")


def run_parallel(fn: Callable[[T], R], items: Sequence[T], max_parallel: int) -> list[R | BaseException]:
    """Run independent calls, retaining input order and individual failures."""
    if max_parallel < 1:
        raise ValueError("max_parallel must be at least 1")
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = [executor.submit(fn, item) for item in items]
        results: list[R | BaseException] = []
        for future in futures:
            try:
                results.append(future.result())
            except BaseException as exc:
                results.append(exc)
    return results
