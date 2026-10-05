from __future__ import annotations

import argparse
from dataclasses import replace
import io
import json
from pathlib import Path
import stat
from urllib.parse import parse_qs
from urllib.request import OpenerDirector, Request

import pytest

from econ_digest.cli import build_parser
from econ_digest.commands import telegraph_setup
from econ_digest.config import Config
from econ_digest.telegraph import TelegraphClient

TOKEN = "synthetic-new-telegraph-token"


class Response(io.BytesIO):
    status = 200


class AccountOpener(OpenerDirector):
    def __init__(self) -> None:
        super().__init__()
        self.payloads: list[dict[str, list[str]]] = []

    def open(self, request: Request, timeout: float = 30) -> Response:
        assert request.full_url == "https://api.telegra.ph/createAccount"
        payload = parse_qs(request.data.decode(), keep_blank_values=True)
        self.payloads.append(payload)
        return Response(json.dumps({"ok": True, "result": {"short_name": "econ-digest", "author_name": "經濟學人導讀",
                                                           "access_token": TOKEN}}).encode())


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, AccountOpener]:
    path = tmp_path / "private" / "env"
    opener = AccountOpener()
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(path))
    monkeypatch.setattr(telegraph_setup, "TelegraphClient", lambda: TelegraphClient(opener=opener))
    return path, opener


def test_setup_preserves_lines_and_mode(delivery_config: Config, setup: tuple[Path, AccountOpener],
                                       capsys: pytest.CaptureFixture[str]) -> None:
    path, opener = setup
    path.parent.mkdir()
    path.write_text("# 密鑰\nTELEGRAM_BOT_TOKEN=synthetic-bot\nOTHER=keep\nTELEGRAPH_ACCESS_TOKEN=old\nTELEGRAPH_ACCESS_TOKEN=duplicate\n")
    path.chmod(0o644)
    assert telegraph_setup.run(argparse.Namespace(force=False), delivery_config) == 0
    assert path.read_text() == "# 密鑰\nTELEGRAM_BOT_TOKEN=synthetic-bot\nOTHER=keep\nTELEGRAPH_ACCESS_TOKEN=" + TOKEN + "\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert opener.payloads == [{"short_name": ["econ-digest"], "author_name": ["經濟學人導讀"], "author_url": [""]}]
    output = capsys.readouterr().out
    assert "econ-digest" in output and "經濟學人導讀" in output
    assert TOKEN not in output and "synthetic-bot" not in output


def test_existing_token_skips_account_and_force_replaces(delivery_config: Config, setup: tuple[Path, AccountOpener],
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    path, opener = setup
    config = replace(delivery_config, secrets=replace(delivery_config.secrets, telegraph_access_token="existing-private-token"))
    assert telegraph_setup.ensure_account(config) == "existing-private-token"
    assert not path.exists() and not opener.payloads
    assert telegraph_setup.ensure_account(config, force=True) == TOKEN
    assert len(opener.payloads) == 1 and TOKEN in path.read_text()
    assert "existing-private-token" not in capsys.readouterr().out


def test_setup_appends_preserving_missing_final_newline(delivery_config: Config, setup: tuple[Path, AccountOpener]) -> None:
    path, _ = setup
    path.parent.mkdir()
    path.write_text("KEEP=unchanged")
    telegraph_setup.ensure_account(delivery_config)
    assert path.read_text() == "KEEP=unchanged\nTELEGRAPH_ACCESS_TOKEN=" + TOKEN + "\n"


def test_setup_registered_command() -> None:
    args = build_parser().parse_args(["telegraph-setup", "--force"])
    assert args.force and args._run is telegraph_setup.run
