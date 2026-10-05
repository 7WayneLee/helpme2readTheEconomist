from pathlib import Path

import pytest

from econ_digest.config import ConfigError, load_config
from econ_digest.logutil import redact


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ECON_DIGEST_CONFIG", raising=False)
    monkeypatch.setenv("ECON_DIGEST_ENV_FILE", str(tmp_path / "env"))


def test_safe_site_backup_and_delivery_defaults(tmp_path):
    config = load_config()
    assert config.paths.output_dir == tmp_path / "output"
    assert not config.site.enabled and config.site.base_url == config.site.ssh_host == config.site.remote_dir == ""
    assert config.site.ssh_timeout_seconds == 30
    assert not config.backup.enabled and config.backup.remote == ""
    assert config.backup.branch == "main"
    assert config.backup.author_name == config.backup.author_email == ""
    assert not config.telegram.cover_photo
    assert not config.telegram.original_text_messages
    assert not config.telegram.send_report_file


@pytest.mark.parametrize("contents,key", [
    ('[site]\nenabled=true', 'site.base_url'),
    ('[site]\nenabled=true\nbase_url="https://site.example"', 'site.ssh_host'),
    ('[site]\nenabled=true\nbase_url="https://site.example"\nssh_host="example-host"', 'site.remote_dir'),
    ('[site]\nssh_timeout_seconds=0', 'site.ssh_timeout_seconds'),
    ('[backup]\nenabled=true', 'backup.remote'),
])
def test_site_backup_validation(tmp_path, contents, key):
    path = tmp_path / "config.toml"
    path.write_text(contents)
    with pytest.raises(ConfigError, match=key):
        load_config(path)


def test_example_loads_with_empty_optional_strings():
    root = Path(__file__).resolve().parents[2]
    config = load_config(root / "config.example.toml")
    assert config.paths.output_dir == root / "output"
    assert not config.site.enabled and not config.backup.enabled
    assert "output/" in (root / ".gitignore").read_text().splitlines()


def test_channel_secret_env_precedence_redaction_and_hidden_repr(tmp_path, monkeypatch):
    (tmp_path / "env").write_text("TELEGRAM_CHANNEL_ID=-100123456789\n")
    config = load_config()
    assert config.secrets.telegram_channel_id == "-100123456789"
    assert config.secrets.telegram_channel_id not in repr(config)
    assert redact("頻道 -100123456789", config.secrets) == "頻道 [已隱藏]"
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@example_channel")
    assert load_config().secrets.telegram_channel_id == "@example_channel"
