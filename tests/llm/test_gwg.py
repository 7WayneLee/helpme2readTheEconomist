"""Exercise the real subprocess transport using a small synthetic gwg."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import pytest

from econ_digest.llm import GwgClient, LLMError
from econ_digest.llm import gwg


SCRIPT = r'''#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

args = sys.argv[1:]
assert args[:2] == ["run", "--"]
assert "-p" in args
assert args[args.index("--output-format") + 1] == "json"
assert "--model" in args
assert "--disable-slash-commands" in args
assert "--json-schema" not in args
assert args[args.index("--print-timeout") + 1].endswith("s")
started = time.monotonic()
assert sys.stdin.read() == ""
assert time.monotonic() - started < 0.2
assert Path.cwd() == Path(os.environ["FAKE_GWG_WORKDIR"])
scenario_path = Path(os.environ["FAKE_GWG_SCENARIO"])
scenario = json.loads(scenario_path.read_text())
index = scenario.get("index", 0)
step = scenario["steps"][min(index, len(scenario["steps"]) - 1)]
scenario["index"] = index + 1
scenario.setdefault("calls", []).append({"args": args, "prompt": args[args.index("-p") + 1], "model": args[args.index("--model") + 1]})
scenario_path.write_text(json.dumps(scenario))
if step.get("sleep"):
    if step.get("child"):
        child_code = "import time; from pathlib import Path; time.sleep(0.8); Path(" + repr(step["marker"]) + ").write_text('survived')"
        child = subprocess.Popen([sys.executable, "-c", child_code])
        with Path(step["pids"]).open("a") as file:
            file.write(str(child.pid) + "\n")
    time.sleep(step["sleep"])
if "stdout" in step:
    print(step["stdout"])
else:
    print(json.dumps(step.get("envelope", {"status": "SUCCESS", "response": '{"ok": true}', "duration_seconds": 1.25, "usage": {"total_tokens": 42}})))
if step.get("stderr"):
    print(step["stderr"], file=sys.stderr)
sys.exit(step.get("exit", 0))
'''


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    executable = tmp_path / "gwg"
    executable.write_text(SCRIPT)
    executable.chmod(0o755)
    scenario_path = tmp_path / "scenario.json"
    workdir = tmp_path / "isolated"
    monkeypatch.setenv("FAKE_GWG_SCENARIO", str(scenario_path))
    monkeypatch.setenv("FAKE_GWG_WORKDIR", str(workdir))

    def create(steps: list[dict[str, Any]], **kwargs: Any) -> tuple[GwgClient, Path]:
        scenario_path.write_text(json.dumps({"steps": steps}))
        return GwgClient(str(executable), workdir=workdir, **kwargs), scenario_path

    return create


def success(response: str = '{"ok": true}') -> dict[str, Any]:
    return {"envelope": {"status": "SUCCESS", "response": response,
                         "duration_seconds": 2.5, "usage": {"total_tokens": 123}}}


def failure(error: str, *, code: int = 400, status: str = "FAILED_PRECONDITION") -> dict[str, Any]:
    return {"exit": 3, "envelope": {"status": "ERROR", "error": error, "response": ""},
            "stderr": "AGY_ERROR: " + json.dumps({"short_error": error, "status": status, "error_code": code})}


@pytest.mark.parametrize("response", [
    '{"ok": true}', '```json\n{"ok": true}\n```', 'Here is the result:\n{"ok": true}\nDone.',
])
def test_success_responses_and_transport_contract(scenario: Any, response: str) -> None:
    client, path = scenario([success(response)])
    result = client.generate_json("test prompt", models=["primary"], stage="classification", timeout=12)
    assert result.data == {"ok": True}
    assert result.model == "primary"
    assert result.total_tokens == 123
    assert result.duration_seconds == 2.5
    assert result.attempts == [{"model": "primary", "outcome": "success", "error": "", "total_tokens": 123, "duration_seconds": 2.5}]
    call = json.loads(path.read_text())["calls"][0]
    assert call["args"][-1] == "12s"
    assert call["prompt"] == "test prompt"


def test_structured_output_is_preferred(scenario: Any) -> None:
    step = success("not json")
    step["envelope"]["structured_output"] = {"nested": {"ok": True}}
    client, _ = scenario([step])
    assert client.generate_json("prompt", models=["primary"]).data == {"nested": {"ok": True}}


def test_extra_read_dirs_are_repeated_and_preserved_on_fallback(scenario: Any, tmp_path: Path) -> None:
    client, path = scenario([failure("quota reached", code=429), success()])
    directories = [tmp_path / "images with spaces", str(tmp_path / "other")]
    client.generate_json("prompt", models=["primary", "fallback"], extra_read_dirs=directories)
    calls = json.loads(path.read_text())["calls"]
    assert len(calls) == 2
    for call in calls:
        args = call["args"]
        assert [args[index + 1] for index, value in enumerate(args) if value == "--add-dir"] == list(map(str, directories))
        assert "--dangerously-skip-permissions" not in args
        assert "--mode" not in args


@pytest.mark.parametrize("error,code,status,kind", [
    ("FAILED_PRECONDITION: User location is not supported for the API use.", 400, "FAILED_PRECONDITION", "location"),
    ("RESOURCE_EXHAUSTED: Individual quota reached. Resets in 34h11m29s.", 429, "RESOURCE_EXHAUSTED", "quota"),
    ("Please sign in again", 401, "UNAUTHENTICATED", "auth"),
])
def test_immediate_model_fallback(scenario: Any, error: str, code: int, status: str, kind: str) -> None:
    client, path = scenario([failure(error, code=code, status=status), success()])
    result = client.generate_json("prompt", models=["gemini", "claude"])
    assert [call["model"] for call in json.loads(path.read_text())["calls"]] == ["gemini", "claude"]
    assert [attempt["outcome"] for attempt in result.attempts] == [kind, "success"]


def test_stderr_json_classifies_without_envelope_error(scenario: Any) -> None:
    step = failure("quota reached", code=429, status="RESOURCE_EXHAUSTED")
    step["envelope"]["error"] = "unknown error"
    client, _ = scenario([step])
    with pytest.raises(LLMError) as caught:
        client.generate_json("prompt", models=["primary"])
    assert caught.value.kind == "quota"
    assert len(caught.value.attempts) == 1


def test_invalid_json_has_one_repair(scenario: Any) -> None:
    client, path = scenario([success('{"bad": }'), success()])
    result = client.generate_json("original", models=["primary", "fallback"])
    calls = json.loads(path.read_text())["calls"]
    assert [call["model"] for call in calls] == ["primary", "primary"]
    assert calls[1]["prompt"].startswith("original\n\n上一次的輸出無法使用（錯誤：")
    assert "請只輸出一個符合要求格式的 JSON 物件" in calls[1]["prompt"]
    assert [attempt["outcome"] for attempt in result.attempts] == ["invalid_output", "success"]


def test_failed_repair_moves_to_next_model(scenario: Any) -> None:
    client, path = scenario([success("no object"), success("[]"), success()])
    result = client.generate_json("original", models=["primary", "fallback"])
    assert [call["model"] for call in json.loads(path.read_text())["calls"]] == ["primary", "primary", "fallback"]
    assert result.model == "fallback"
    assert json.loads(path.read_text())["calls"][2]["prompt"] == "original"


def test_validation_failure_repairs(scenario: Any) -> None:
    client, _ = scenario([success('{"ok": false}'), success()])

    def validate(data: dict[str, Any]) -> None:
        if data.get("ok") is not True:
            raise ValueError("ok must be true")

    result = client.generate_json("prompt", models=["primary"], validate=validate)
    assert "ok must be true" in result.attempts[0]["error"]
    assert result.data == {"ok": True}


def test_no_account_backoff_and_retry(scenario: Any) -> None:
    sleeps: list[float] = []
    client, path = scenario([{"exit": 75}] * 3 + [success()], sleep=sleeps.append, no_account_wait=210)
    result = client.generate_json("prompt", models=["primary", "fallback"])
    assert sleeps == [30, 60, 120]
    assert len(result.attempts) == 4
    assert [call["model"] for call in json.loads(path.read_text())["calls"]] == ["primary"] * 4


def test_no_account_budget_is_clipped_and_exhausted(scenario: Any) -> None:
    sleeps: list[float] = []
    client, _ = scenario([{"exit": 75}], sleep=sleeps.append, no_account_wait=45)
    with pytest.raises(LLMError) as caught:
        client.generate_json("prompt", models=["primary", "fallback"])
    assert sleeps == [30, 15]
    assert caught.value.kind == "no_account"
    assert len(caught.value.attempts) == 3


def test_other_error_retries_once_then_falls_back(scenario: Any) -> None:
    client, path = scenario([failure("internal error", code=500, status="INTERNAL")] * 2 + [success()])
    result = client.generate_json("prompt", models=["primary", "fallback"])
    assert [call["model"] for call in json.loads(path.read_text())["calls"]] == ["primary", "primary", "fallback"]
    assert [attempt["outcome"] for attempt in result.attempts] == ["error", "error", "success"]


def test_all_failed_error_keeps_last_kind_and_attempts(scenario: Any) -> None:
    client, _ = scenario([failure("location not supported"), failure("quota reached", code=429)])
    with pytest.raises(LLMError) as caught:
        client.generate_json("prompt", models=["first", "second"])
    assert caught.value.kind == "quota"
    assert [attempt["model"] for attempt in caught.value.attempts] == ["first", "second"]


def test_timeout_kills_entire_process_group(scenario: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gwg, "_TIMEOUT_GRACE", 0.15)
    marker = tmp_path / "child-survived"
    pids = tmp_path / "child-pids"
    client, _ = scenario([{"sleep": 5, "child": True, "marker": str(marker), "pids": str(pids)}], call_timeout=0.05)
    started = time.monotonic()
    with pytest.raises(LLMError) as caught:
        client.generate_json("prompt", models=["primary"])
    assert caught.value.kind == "timeout"
    assert len(caught.value.attempts) == 2
    assert time.monotonic() - started < 3
    assert len(pids.read_text().splitlines()) == 2
    for pid in pids.read_text().splitlines():
        status = Path(f"/proc/{pid}/status")
        if status.exists():
            state = next(line for line in status.read_text().splitlines() if line.startswith("State:"))
            assert "Z" in state or "X" in state
    assert not marker.exists()


@pytest.mark.parametrize("prompt", ["x" * 100_001, "中" * 33_334])
def test_prompt_size_guard(scenario: Any, prompt: str) -> None:
    client, path = scenario([success()])
    with pytest.raises(ValueError, match="100,000 UTF-8 bytes"):
        client.generate_json(prompt, models=["primary"])
    assert json.loads(path.read_text()).get("index", 0) == 0


def test_prompt_size_limit_is_inclusive(scenario: Any) -> None:
    client, _ = scenario([success()])
    assert client.generate_json("x" * 100_000, models=["primary"]).data == {"ok": True}


def test_repair_has_room_even_at_input_size_limit(scenario: Any) -> None:
    client, _ = scenario([success("invalid output"), success()])
    result = client.generate_json("x" * 100_000, models=["primary"])
    assert result.data == {"ok": True}
    assert len(result.attempts) == 2


@pytest.mark.parametrize("stdout", ["not an envelope", "[]"])
def test_invalid_envelope_can_be_repaired(scenario: Any, stdout: str) -> None:
    client, _ = scenario([{"stdout": stdout}, success()])
    result = client.generate_json("prompt", models=["primary"])
    assert result.attempts[0]["outcome"] == "invalid_output"


def test_info_logs_do_not_contain_prompt(scenario: Any, caplog: pytest.LogCaptureFixture) -> None:
    client, _ = scenario([success()])
    with caplog.at_level(logging.INFO):
        client.generate_json("PRIVATE_SYNTHETIC_TEXT", models=["primary"], stage="summary")
    assert "PRIVATE_SYNTHETIC_TEXT" not in caplog.text
    assert "stage=summary model=primary outcome=success tokens=123 seconds=2.500" in caplog.text


def test_missing_executable_is_a_retried_error(tmp_path: Path) -> None:
    client = GwgClient(str(tmp_path / "missing-gwg"), workdir=tmp_path / "work")
    with pytest.raises(LLMError) as caught:
        client.generate_json("prompt", models=["primary"])
    assert caught.value.kind == "error"
    assert len(caught.value.attempts) == 2


@pytest.mark.skipif(os.environ.get("ECON_DIGEST_LIVE_GWG") != "1", reason="live gwg consumes shared quota")
def test_live_gwg_smoke(tmp_path: Path) -> None:
    result = GwgClient(workdir=tmp_path / "gwg-work", no_account_wait=0).generate_json(
        '請只輸出一個 JSON 物件：{"ok": true}，不要有任何其他文字。',
        models=["gemini-3.8-flash-high"], stage="live-smoke",
    )
    assert result.data == {"ok": True}
    assert result.total_tokens > 0
    print(f"model={result.model} tokens={result.total_tokens} seconds={result.duration_seconds}")
