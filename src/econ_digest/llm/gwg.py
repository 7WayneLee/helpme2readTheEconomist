"""Headless gwg transport with isolated cwd and process-group timeouts."""

import json
import math
import os
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ._retry import Attempt, JSONClient, classify_error

_TIMEOUT_GRACE = 60.0


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
        if math.isfinite(result) and result >= 0:
            return result
    return 0.0


class GwgClient(JSONClient):
    def __init__(self, gwg_bin: str = "gwg", *, workdir: Path, call_timeout: float = 300,
                 no_account_wait: float = 900, sleep: Callable[[float], None] = time.sleep) -> None:
        super().__init__(call_timeout=call_timeout, no_account_wait=no_account_wait, sleep=sleep)
        self.gwg_bin = gwg_bin
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _invoke(self, prompt: str, model: str, stage: str, timeout: float,
                extra_read_dirs: Sequence[str | Path] = ()) -> Attempt:
        command = [self.gwg_bin, "run", "--", "-p", prompt, "--output-format", "json",
                   "--model", model, "--disable-slash-commands", "--print-timeout", f"{int(timeout)}s"]
        for directory in extra_read_dirs:
            command.extend(("--add-dir", str(directory)))
        started = time.monotonic()
        try:
            process = subprocess.Popen(command, cwd=self.workdir, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="replace", start_new_session=True)
        except OSError as exc:
            return Attempt(kind="error", error=str(exc), duration_seconds=time.monotonic() - started)
        try:
            stdout, stderr = process.communicate(timeout=timeout + _TIMEOUT_GRACE)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            return Attempt(kind="timeout", error=f"gwg exceeded hard timeout of {timeout + _TIMEOUT_GRACE:g}s",
                           duration_seconds=time.monotonic() - started)
        wall_time = time.monotonic() - started
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as exc:
            kind = classify_error(stderr, process.returncode) if process.returncode else "invalid_output"
            return Attempt(kind=kind, error=stderr.strip() or f"Invalid gwg envelope: {exc.msg}",
                           duration_seconds=wall_time)
        if not isinstance(envelope, dict):
            return Attempt(kind=classify_error(stderr, process.returncode) if process.returncode else "invalid_output",
                           error="gwg envelope must be a JSON object", duration_seconds=wall_time)
        usage = envelope.get("usage")
        tokens = int(_number(usage.get("total_tokens"))) if isinstance(usage, dict) else 0
        seconds = _number(envelope.get("duration_seconds")) if "duration_seconds" in envelope else wall_time
        if process.returncode != 0 or envelope.get("status") != "SUCCESS":
            errors = [str(envelope.get("error") or "")]
            for line in stderr.splitlines():
                if "AGY_ERROR:" in line:
                    try:
                        detail = json.loads(line.split("AGY_ERROR:", 1)[1].strip())
                    except json.JSONDecodeError:
                        continue
                    if isinstance(detail, dict):
                        errors.extend(str(detail[key]) for key in ("short_error", "status", "error_code") if key in detail)
            errors.append(stderr.strip())
            message = " | ".join(part for part in errors if part) or f"gwg exited {process.returncode}"
            return Attempt(kind=classify_error(message, process.returncode), error=message,
                           total_tokens=tokens, duration_seconds=seconds)
        structured = envelope.get("structured_output")
        output = structured if isinstance(structured, dict) else envelope.get("response")
        return Attempt(output=output, total_tokens=tokens, duration_seconds=seconds)
