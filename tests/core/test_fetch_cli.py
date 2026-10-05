from __future__ import annotations

import io
import http.client
import json
import logging
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from econ_digest import cli
from econ_digest.commands import load_or_parse_issue
from econ_digest.config import Config, PathsConfig, SecretsConfig
from econ_digest.fetch import FetchError, Fetcher, issue_directory, normalize_issue_date
from econ_digest.logutil import configure_logging
from econ_digest.models import Issue, save_json


class MockOpener:
    def __init__(self, responses: list[bytes | Exception]) -> None:
        self.responses = responses
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[int] = []

    def open(self, request: urllib.request.Request, *, timeout: int) -> io.BytesIO:
        self.requests.append(request)
        self.timeouts.append(timeout)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(response)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(paths=PathsConfig(tmp_path / "data"))


def test_listing_latest_filtering_and_headers(config: Config) -> None:
    entries = [
        {"name": "te_2026.09.26", "type": "dir"}, {"name": "te_2026.10.03", "type": "dir"},
        {"name": "te_2026.10.10", "type": "file"}, {"name": "unrelated", "type": "dir"},
        {"name": "te_2026.02.30", "type": "dir"}, {"name": "te_2026.10.03extra", "type": "dir"},
    ]
    payload = json.dumps(entries).encode()
    config = replace(config, secrets=SecretsConfig(github_token="synthetic-token"))
    opener = MockOpener([payload, payload])
    fetcher = Fetcher(config, opener=opener)
    assert fetcher.list_issue_dates() == ["2026.09.26", "2026.10.03"]
    assert fetcher.latest_issue_date() == "2026.10.03"
    assert opener.requests[0].full_url == "https://api.github.com/repos/hehonghui/awesome-english-ebooks/contents/01_economist?ref=master"
    assert opener.requests[0].get_header("User-agent") == "econ-digest"
    assert opener.requests[0].get_header("Authorization") == "Bearer synthetic-token"
    assert opener.timeouts == [30, 30]


def test_no_auth_without_token_and_no_issues_error(config: Config) -> None:
    opener = MockOpener([b"[]"])
    with pytest.raises(FetchError, match="沒有有效"):
        Fetcher(config, opener=opener).latest_issue_date()
    assert opener.requests[0].get_header("Authorization") is None


@pytest.mark.parametrize("spec,expected", [("2026.10.03", "2026.10.03"), ("2026-10-03", "2026.10.03")])
def test_explicit_issue_date_resolution_without_network(config: Config, spec: str, expected: str) -> None:
    assert Fetcher(config, opener=MockOpener([])).resolve_issue(spec) == expected


@pytest.mark.parametrize("spec", ["2026.2.3", "2026.02.30", "../2026.10.03", "2026-10.03", "latest "])
def test_bad_issue_specs(spec: str) -> None:
    with pytest.raises(FetchError):
        normalize_issue_date(spec)


def test_download_atomic_skip_valid_cache_and_replace_corruption(config: Config, synthetic_epub: Path) -> None:
    opener = MockOpener([synthetic_epub.read_bytes(), synthetic_epub.read_bytes()])
    fetcher = Fetcher(config, opener=opener)
    target = fetcher.download_issue("2026.10.03")
    assert target == config.paths.data_dir / "issues/te_2026.10.03/TheEconomist.2026.10.03.epub"
    assert target.read_bytes() == synthetic_epub.read_bytes()
    assert fetcher.download_issue("2026.10.03") == target
    assert len(opener.requests) == 1
    target.write_text("corrupt", encoding="utf-8")
    assert fetcher.download_issue("2026.10.03").read_bytes() == synthetic_epub.read_bytes()
    assert len(opener.requests) == 2
    assert len(list(target.parent.iterdir())) == 1
    assert opener.requests[0].get_header("Authorization") is None


def test_download_retries_transient_and_invalid_zip(config: Config, synthetic_epub: Path) -> None:
    sleeps: list[float] = []
    opener = MockOpener([
        urllib.error.URLError("synthetic disconnect"),
        urllib.error.HTTPError("https://example.invalid", 503, "unavailable", {}, None),
        b"not a zip", synthetic_epub.read_bytes(),
    ])
    target = Fetcher(config, opener=opener, sleep=sleeps.append).download_issue("2026.10.03")
    assert target.exists()
    assert sleeps == [1.0, 2.0, 4.0]
    assert len(opener.requests) == 4
    assert list(target.parent.iterdir()) == [target]


def test_retry_exhaustion_cleanup_and_error_redaction(config: Config) -> None:
    opener = MockOpener([urllib.error.URLError("synthetic-secret") for _ in range(4)])
    with pytest.raises(FetchError) as info:
        Fetcher(config, opener=opener, sleep=lambda _: None).download_issue("2026.10.03")
    assert "重試 3 次" in str(info.value)
    assert "synthetic-secret" not in str(info.value)
    assert not list(issue_directory(config, "2026.10.03").iterdir())


def test_permanent_404_does_not_retry(config: Config) -> None:
    opener = MockOpener([urllib.error.HTTPError("https://example.invalid", 404, "not found", {}, None)])
    with pytest.raises(FetchError, match="HTTP 404"):
        Fetcher(config, opener=opener).download_issue("2026.10.03")
    assert len(opener.requests) == 1


def test_malformed_listing_retry(config: Config) -> None:
    opener = MockOpener([b"not json", b"{}", b'[{"name":"te_2026.10.03","type":"dir"}]'])
    sleeps: list[float] = []
    assert Fetcher(config, opener=opener, sleep=sleeps.append).resolve_issue("latest") == "2026.10.03"
    assert sleeps == [1, 2]


def test_incomplete_download_is_retried(config: Config, synthetic_epub: Path) -> None:
    opener = MockOpener([http.client.IncompleteRead(b"partial", 10), synthetic_epub.read_bytes()])
    sleeps: list[float] = []
    assert Fetcher(config, opener=opener, sleep=sleeps.append).download_issue("2026.10.03").exists()
    assert sleeps == [1]


def test_shared_helper_fetches_then_reads_cache(config: Config, synthetic_epub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opener = MockOpener([synthetic_epub.read_bytes()])
    monkeypatch.setattr(urllib.request, "urlopen", opener.open)
    issue = load_or_parse_issue(config, "2026-10-03")
    assert len(issue.articles) == 8
    assert (issue_directory(config, issue.issue_date) / "issue.json").exists()
    assert load_or_parse_issue(config, "2026.10.03") == issue
    assert len(opener.requests) == 1


@pytest.fixture
def cli_config(config: Config, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setattr(cli, "load_config", lambda _: config)
    return config


def test_fetch_command(cli_config: Config, synthetic_epub: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", MockOpener([synthetic_epub.read_bytes()]).open)
    assert cli.main(["fetch", "--issue", "2026.10.03"]) == 0
    assert capsys.readouterr().out.strip().endswith("TheEconomist.2026.10.03.epub")


def test_parse_and_signals_commands(cli_config: Config, synthetic_issue: Issue, capsys: pytest.CaptureFixture[str]) -> None:
    save_json(issue_directory(cli_config, synthetic_issue.issue_date) / "issue.json", synthetic_issue)
    assert cli.main(["parse", "--issue", "2026.10.03"]) == 0
    output = capsys.readouterr().out
    assert "Finance & economics\t1\t11" in output
    assert "The world this week\t3\t15" in output
    assert "合計\t8\t" in output
    assert cli.main(["signals", "--issue", "2026.10.03"]) == 0
    output = capsys.readouterr().out
    assert "A synthetic column" in output
    assert "提及次數：2；詞彙：Taiwan, TSMC" in output


def test_unimplemented_command_and_global_options(cli_config: Config, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    original = cli.importlib.import_module

    def import_module(name: str) -> Any:
        if name == "econ_digest.commands.analyze":
            raise ModuleNotFoundError("Synthetic missing command", name=name)
        return original(name)

    monkeypatch.setattr(cli.importlib, "import_module", import_module)
    assert cli.main(["--config", "synthetic.toml", "-v", "analyze"]) == 2
    assert "此功能尚未實作" in capsys.readouterr().err
    assert "（尚未實作）" in cli.build_parser().format_help()


def test_dependency_import_errors_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    original = cli.importlib.import_module

    def import_module(name: str) -> Any:
        if name == "econ_digest.commands.analyze":
            raise ModuleNotFoundError("Missing command dependency", name="imaginary_dependency")
        return original(name)

    monkeypatch.setattr(cli.importlib, "import_module", import_module)
    with pytest.raises(ModuleNotFoundError) as info:
        cli.build_parser()
    assert info.value.name == "imaginary_dependency"


def test_external_command_registration_and_hyphen_mapping(monkeypatch: pytest.MonkeyPatch, cli_config: Config) -> None:
    original = cli.importlib.import_module
    seen: list[str] = []

    class Extension:
        @staticmethod
        def configure(parser: Any) -> None:
            parser.add_argument("--synthetic", required=True)

        @staticmethod
        def run(args: Any, config: Config) -> int:
            assert args.synthetic == "yes"
            return 7

    def import_module(name: str) -> Any:
        seen.append(name)
        return Extension if name.endswith(".telegram_setup") else original(name)

    monkeypatch.setattr(cli.importlib, "import_module", import_module)
    assert cli.main(["telegram-setup", "--synthetic", "yes"]) == 7
    assert "econ_digest.commands.telegram_setup" in seen


def test_logging_stderr_file_and_secret_redaction(config: Config, capsys: pytest.CaptureFixture[str]) -> None:
    config = replace(config, secrets=SecretsConfig(telegram_bot_token="12345:synthetic-secret", github_token="synthetic-github"))
    configure_logging(config)
    logging.getLogger("synthetic").warning("URL %s and %s", "https://api.telegram.org/bot12345:synthetic-secret/sendMessage", "synthetic-github")
    stderr = capsys.readouterr().err
    file = (config.paths.data_dir / "logs/econ-digest.log").read_text(encoding="utf-8")
    for output in (stderr, file):
        assert "synthetic-secret" not in output and "synthetic-github" not in output
        assert "[已隱藏]" in output


def test_python_module_entrypoint() -> None:
    result = subprocess.run([sys.executable, "-m", "econ_digest", "--help"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "telegram-setup" in result.stdout
