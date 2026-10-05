from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_rendered_units_pass_systemd_verify(tmp_path: Path) -> None:
    analyzer = shutil.which("systemd-analyze")
    if analyzer is None:
        pytest.skip("systemd-analyze is unavailable")
    repo = Path(__file__).resolve().parents[2]
    destination = tmp_path / "rendered units"
    guard_dir = tmp_path / "guard"
    guard_dir.mkdir()
    systemctl = guard_dir / "systemctl"
    systemctl.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    systemctl.chmod(0o755)
    environment = {**os.environ, "PATH": f"{guard_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                   "XDG_CONFIG_HOME": str(tmp_path / "config")}
    rendered = subprocess.run([str(repo / "deploy/install-user-timer.sh"), "--print-units", str(destination)],
                              env=environment, capture_output=True, text=True)
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    service = destination / "econ-digest.service"
    timer = destination / "econ-digest.timer"
    content = service.read_text(encoding="utf-8")
    assert f"WorkingDirectory={str(repo).replace('%', '%%')}\n" in content
    assert f'ExecStart="{repo}/.venv/bin/econ-digest" run\n' in content
    assert "@REPO@" not in content
    assert timer.read_text() == (repo / "deploy/systemd/econ-digest.timer").read_text()
    verification = subprocess.run([analyzer, "--user", "verify", str(service), str(timer)],
                                  capture_output=True, text=True)
    assert verification.returncode == 0, verification.stdout + verification.stderr
    assert not (tmp_path / "config").exists()
