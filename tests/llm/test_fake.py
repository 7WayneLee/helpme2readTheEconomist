import threading
import time
from typing import Any

import pytest

from econ_digest.llm import FakeLLMClient, LLMError, run_parallel


def test_fake_returns_dict_and_records_calls() -> None:
    client = FakeLLMClient(lambda prompt, model, stage: {"prompt": prompt, "model": model, "stage": stage})
    result = client.generate_json("request", models=["primary"], stage="summaries")
    assert result.data == {"prompt": "request", "model": "primary", "stage": "summaries"}
    assert client.calls == [("request", "primary", "summaries")]
    assert result.total_tokens == 0
    assert result.duration_seconds >= 0


def test_fake_uses_the_same_repair_and_fallback_policy() -> None:
    def respond(prompt: str, model: str, stage: str) -> str | Exception:
        if model == "primary":
            return LLMError("location not supported", kind="location")
        if "上一次的輸出無法使用" not in prompt:
            return "not json"
        return '```json\n{"ok":true}\n```'

    client = FakeLLMClient(respond)
    result = client.generate_json("request", models=["primary", "fallback"], stage="selection")
    assert result.data == {"ok": True}
    assert [call[1] for call in client.calls] == ["primary", "fallback", "fallback"]
    assert [attempt["outcome"] for attempt in result.attempts] == ["location", "invalid_output", "success"]


def test_fake_retries_raised_exception_once() -> None:
    def respond(prompt: str, model: str, stage: str) -> dict[str, Any]:
        if model == "primary":
            raise RuntimeError("service unavailable")
        return {"ok": True}

    client = FakeLLMClient(respond)
    assert client.generate_json("request", models=["primary", "fallback"]).model == "fallback"
    assert [call[1] for call in client.calls] == ["primary", "primary", "fallback"]


def test_fake_validation_repair() -> None:
    def validate(data: dict[str, Any]) -> None:
        if data.get("count") != 1:
            raise ValueError("count must be 1")

    client = FakeLLMClient(lambda prompt, model, stage: {"count": 1 if "上一次" in prompt else 0})
    assert client.generate_json("request", models=["primary"], validate=validate).data == {"count": 1}
    assert len(client.calls) == 2


def test_fake_value_error_is_invalid_output() -> None:
    client = FakeLLMClient(lambda prompt, model, stage: ValueError("synthetic bad output"))
    with pytest.raises(LLMError) as caught:
        client.generate_json("request", models=["primary", "fallback"])
    assert caught.value.kind == "invalid_output"
    assert len(caught.value.attempts) == 4


def test_fake_no_account_backoff_without_waiting() -> None:
    sleeps: list[float] = []
    client = FakeLLMClient(lambda prompt, model, stage: LLMError("busy", kind="no_account"),
                           sleep=sleeps.append, no_account_wait=35)
    with pytest.raises(LLMError) as caught:
        client.generate_json("request", models=["primary"])
    assert caught.value.kind == "no_account"
    assert sleeps == [30, 5]


def test_fake_timeout_exception_is_retried_and_classified() -> None:
    client = FakeLLMClient(lambda prompt, model, stage: TimeoutError("synthetic deadline"))
    with pytest.raises(LLMError) as caught:
        client.generate_json("request", models=["primary"])
    assert caught.value.kind == "timeout"
    assert len(caught.value.attempts) == 2


def test_client_and_calls_are_thread_safe() -> None:
    client = FakeLLMClient(lambda prompt, model, stage: {"value": prompt})
    results = run_parallel(lambda item: client.generate_json(str(item), models=["primary"]), list(range(30)), 5)
    assert [result.data["value"] for result in results] == [str(index) for index in range(30)]  # type: ignore[union-attr]
    assert len(client.calls) == 30


def test_parallel_preserves_order_captures_base_exceptions_and_limits_workers() -> None:
    lock = threading.Lock()
    active = 0
    peak = 0

    def process(index: int) -> int:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep((5 - index) * 0.01)
            if index == 2:
                raise KeyboardInterrupt("synthetic interruption")
            if index == 3:
                raise ValueError("synthetic failure")
            return index * 2
        finally:
            with lock:
                active -= 1

    results = run_parallel(process, list(range(5)), 2)
    assert results[:2] == [0, 2]
    assert isinstance(results[2], KeyboardInterrupt)
    assert isinstance(results[3], ValueError)
    assert results[4] == 8
    assert peak == 2


def test_parallel_empty_and_invalid_worker_count() -> None:
    assert run_parallel(lambda item: item, [], 1) == []
    with pytest.raises(ValueError, match="at least 1"):
        run_parallel(lambda item: item, [], 0)


@pytest.mark.parametrize("kwargs", [{"models": []}, {"models": ["primary"], "timeout": 0}, {"models": ["primary"], "timeout": float("nan")}])
def test_invalid_parameters(kwargs: dict[str, Any]) -> None:
    client = FakeLLMClient(lambda prompt, model, stage: {})
    with pytest.raises(ValueError):
        client.generate_json("request", **kwargs)
    assert client.calls == []
