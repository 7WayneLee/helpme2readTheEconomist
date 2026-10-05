from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from econ_digest.config import ConfigError, load_config


@pytest.fixture(autouse=True)
def isolate_config_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("ECON_DIGEST_CONFIG", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GITHUB_TOKEN", "TELEGRAPH_ACCESS_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(tmp_path / "no-env-file"))


def test_defaults_and_frozen_tree(tmp_path: Path) -> None:
    config = load_config()
    assert config.paths.data_dir == tmp_path / "data"
    assert config.source.repo == "hehonghui/awesome-english-ebooks"
    assert config.source.branch == "master"
    assert config.llm.max_parallel == 2
    assert config.llm.models.classify == ("gemini-3.8-flash-high", "claude-sonnet-4-6")
    assert config.llm.models.focus == ("gemini-3.8-flash-high", "claude-sonnet-4-6")
    assert config.analysis.focus_count == 3
    assert config.english.min_words == 600
    assert config.english.level.startswith("全民英檢中級")
    assert config.telegram.message_delay_seconds == 1.1
    assert config.telegram.delivery == "telegraph"
    assert config.telegram.send_report_file is False
    assert config.telegram.cover_photo is False
    assert config.report.embed_images is True
    assert config.telegraph.author_name == "經濟學人導讀"
    assert config.telegraph.author_url == ""
    assert config.telegraph.page_limit_bytes == 60000
    assert config.secrets.telegraph_access_token is None
    assert config.secrets.telegram_bot_token is None
    with pytest.raises(FrozenInstanceError):
        config.llm.max_parallel = 3  # type: ignore[misc]


def test_resolution_precedence_and_relative_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local = tmp_path / "config.toml"
    local.write_text('[paths]\ndata_dir = "local"\n', encoding="utf-8")
    assert load_config().paths.data_dir == tmp_path / "local"
    directory = tmp_path / "settings"
    directory.mkdir()
    environment = directory / "environment.toml"
    environment.write_text('[paths]\ndata_dir = "env-data"\n', encoding="utf-8")
    monkeypatch.setenv("ECON_DIGEST_CONFIG", str(environment))
    assert load_config().paths.data_dir == directory / "env-data"
    explicit = directory / "explicit.toml"
    explicit.write_text('[paths]\ndata_dir = "cli-data"\n', encoding="utf-8")
    assert load_config(explicit).paths.data_dir == directory / "cli-data"


def test_nested_overrides_and_tier_defaults(tmp_path: Path) -> None:
    path = tmp_path / "custom.toml"
    path.write_text('''[llm]
max_parallel = 4
[llm.models]
classify = ["custom-primary", "custom-fallback"]
[tiers.category]
finance = "B"
[tiers]
force_tier_by_kind = {}
''', encoding="utf-8")
    config = load_config(path)
    assert config.llm.max_parallel == 4
    assert config.llm.models.classify == ("custom-primary", "custom-fallback")
    assert config.llm.models.english[0] == "gemini-3.8-flash-high"
    assert config.tiers.category["finance"] == "B"
    assert config.tiers.category["intl.us"] == "C"
    assert not config.tiers.force_tier_by_kind


@pytest.mark.parametrize("content,key", [
    ('[llm]\nmax_parallel = "2"', "llm.max_parallel"),
    ('[llm]\nmax_parallel = true', "llm.max_parallel"),
    ('[llm]\nmax_parallel = 0', "llm.max_parallel"),
    ('[llm]\nbackend = "agy"', "llm.backend"),
    ('[llm.models]\nclassify = []', "llm.models.classify"),
    ('[llm.models]\nclassify = [42]', "llm.models.classify[0]"),
    ('[llm.models]\nfocus = []', "llm.models.focus"),
    ('[analysis]\nfocus_count = 0', "analysis.focus_count"),
    ('[analysis]\nfocus_count = -1', "analysis.focus_count"),
    ('[analysis]\nfocus_count = true', "analysis.focus_count"),
    ('[analysis]\nfocus_count = "3"', "analysis.focus_count"),
    ('[paths]\ndata_dir = 3', "paths.data_dir"),
    ('[telegram]\nenabled = "true"', "telegram.enabled"),
    ('[telegram]\ncover_photo = "true"', "telegram.cover_photo"),
    ('[report]\nembed_images = "true"', "report.embed_images"),
    ('[telegram]\nmessage_delay_seconds = -1', "telegram.message_delay_seconds"),
    ('[telegram]\nmessage_delay_seconds = nan', "telegram.message_delay_seconds"),
    ('[telegram]\ndelivery = "other"', "telegram.delivery"),
    ('[telegraph]\npage_limit_bytes = 0', "telegraph.page_limit_bytes"),
    ('[telegraph]\npage_limit_bytes = 64001', "telegraph.page_limit_bytes"),
    ('[telegraph]\npage_limit_bytes = true', "telegraph.page_limit_bytes"),
    ('[telegraph]\nauthor_name = ""', "telegraph.author_name"),
    ('[english]\nmax_words = 100', "english.max_words"),
    ('[tiers.taiwan]\n"1" = "F"', "tiers.taiwan.1"),
    ('[source]\nrepo = "bad"', "source.repo"),
    ('[source]\nfolder = "../other"', "source.folder"),
    ('llm = []', "llm"),
])
def test_invalid_values_name_key(tmp_path: Path, content: str, key: str) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert key in str(info.value)


def test_unknown_keys_warn_and_are_ignored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "unknown.toml"
    path.write_text('unknown = "private-value"\n[llm]\nother = 7\n[tiers.category]\nunknown = "F"', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        load_config(path)
    assert "unknown" in caplog.text and "llm.other" in caplog.text
    assert "tiers.category.unknown" in caplog.text
    assert "private-value" not in caplog.text


def test_secrets_env_file_and_environment_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "secrets"
    path.write_text('# comment\nTELEGRAM_BOT_TOKEN="private-token"\nTELEGRAM_CHAT_ID=1234\nGITHUB_TOKEN=private-github\nignored line\n', encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "existing-token")
    config = load_config()
    assert config.secrets.telegram_bot_token == "existing-token"
    assert config.secrets.telegram_chat_id == "1234"
    assert config.secrets.github_token == "private-github"
    assert "private-token" not in caplog.text and "private-github" not in caplog.text
    assert "existing-token" not in repr(config.secrets)
    assert "existing-token" not in repr(config)
    assert "群組" not in caplog.text


def test_env_file_permission_warning(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "readable-env"
    path.write_text("TELEGRAM_BOT_TOKEN=secret-value\n", encoding="utf-8")
    path.chmod(0o644)
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(path))
    load_config()
    assert "群組或其他使用者讀取" in caplog.text
    assert "secret-value" not in caplog.text


def test_explicit_missing_file_and_invalid_toml(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="找不到設定檔"):
        load_config(tmp_path / "missing.toml")
    path = tmp_path / "syntax.toml"
    path.write_text('[broken\nsecret="never-print"', encoding="utf-8")
    with pytest.raises(ConfigError, match="TOML") as info:
        load_config(path)
    assert "never-print" not in str(info.value)


def test_example_matches_defaults(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "config.example.toml"
    default = load_config()
    configured = load_config(example)
    assert configured.llm == default.llm
    assert configured.tiers == default.tiers
    assert configured.analysis == default.analysis
    assert configured.source == default.source
    assert configured.english == default.english
    assert configured.telegram == default.telegram
    assert configured.telegraph == default.telegraph


def test_telegraph_env_secret_precedence_and_redaction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                     caplog: pytest.LogCaptureFixture) -> None:
    from econ_digest.logutil import _RedactingFormatter, redact
    path = tmp_path / "env"
    path.write_text('TELEGRAPH_ACCESS_TOKEN="file-secret-telegraph"\n')
    path.chmod(0o600)
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(path))
    config = load_config()
    assert config.secrets.telegraph_access_token == "file-secret-telegraph"
    monkeypatch.setenv("TELEGRAPH_ACCESS_TOKEN", "environment-secret-telegraph")
    config = load_config()
    assert config.secrets.telegraph_access_token == "environment-secret-telegraph"
    assert "environment-secret-telegraph" not in repr(config.secrets)
    assert "environment-secret-telegraph" not in repr(config)
    assert "file-secret-telegraph" not in caplog.text
    error = RuntimeError("error: environment-secret-telegraph")
    assert "environment-secret-telegraph" not in redact(str(error), config.secrets)
    record = logging.LogRecord("test", logging.ERROR, "", 1, "%s", (error,), None)
    assert "environment-secret-telegraph" not in _RedactingFormatter(config.secrets).format(record)


def test_relative_executable_paths_follow_config_directory(tmp_path: Path) -> None:
    folder = tmp_path / "settings"
    folder.mkdir()
    path = folder / "custom.toml"
    path.write_text('[llm]\ngwg_bin = "../tools/gwg"', encoding="utf-8")
    assert load_config(path).llm.gwg_bin == str(tmp_path / "tools/gwg")
    path.write_text('[llm]\ngwg_bin = "gwg-custom"', encoding="utf-8")
    assert load_config(path).llm.gwg_bin == "gwg-custom"


def test_focus_configuration_overrides(tmp_path: Path) -> None:
    path = tmp_path / "focus.toml"
    path.write_text('[analysis]\nfocus_count = 2\n[llm.models]\nfocus = ["custom-focus"]')
    config = load_config(path)
    assert config.analysis.focus_count == 2
    assert config.llm.models.focus == ("custom-focus",)
