from dataclasses import replace
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from econ_digest.cli import main
from econ_digest.commands.social import run
from econ_digest.config import ConfigError, load_config
from econ_digest.logutil import redact
from econ_digest.social.queue import Queue


def test_preview_cli_is_offline_and_does_not_enqueue(issue_directory, social_config, monkeypatch, capsys):
    monkeypatch.setattr('econ_digest.cli.load_config', lambda _: social_config)
    assert main(['social', 'threads', 'preview', '--issue', '2026.10.03']) == 0
    output = capsys.readouterr().out
    assert '[1/5] 本週導讀' in output and '/500 字元' in output
    assert '共 5 則貼文' in output and '【台灣】' in output
    assert 'synthetic-private-token' not in output and 'synthetic-user' not in output
    assert not Queue(social_config.paths.data_dir).path.exists()


def test_enqueue_status_pause_and_resume_cli(issue_directory, social_config, monkeypatch, capsys):
    monkeypatch.setattr('econ_digest.cli.load_config', lambda _: social_config)
    assert main(['social', 'threads', 'enqueue', '--issue', '2026.10.03']) == 0
    assert '已加入 5 則' in capsys.readouterr().out
    assert main(['social', 'threads', 'enqueue', '--issue', '2026.10.03']) == 0
    assert '已加入 0 則' in capsys.readouterr().out
    assert main(['social', 'threads', 'status']) == 0
    output = capsys.readouterr().out
    assert '已發布 0/5' in output and '權杖年齡' in output
    assert 'synthetic-private-token' not in output and 'synthetic-user' not in output
    assert main(['social', 'threads', 'pause']) == 0
    assert Queue(social_config.paths.data_dir).load()['paused']
    assert main(['social', 'threads', 'resume']) == 0
    assert not Queue(social_config.paths.data_dir).load()['paused']
    assert main(['social', 'threads', 'post-next', '--dry-run']) == 0


def test_defaults_and_secret_loading(tmp_path, monkeypatch):
    env = tmp_path / 'env'
    env.write_text('THREADS_ACCESS_TOKEN="synthetic-private"\nTHREADS_USER_ID=synthetic-profile\nTHREADS_TOKEN_ISSUED_AT=2026-10-06T00:00:00+00:00\n')
    env.chmod(0o600)
    for key in ('THREADS_ACCESS_TOKEN', 'THREADS_USER_ID', 'THREADS_TOKEN_ISSUED_AT'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('ECON_DIGEST_ENV_FILE', str(env))
    config_file = tmp_path / 'config.toml'
    config_file.write_text('')
    config = load_config(config_file)
    assert not config.social.threads.enabled
    assert config.social.threads.sections == ('台灣', '本週焦點', '國際', '財經・科技・文化')
    assert config.social.threads.interval_minutes == 60 and config.social.threads.max_per_day == 15
    assert config.secrets.threads_access_token == 'synthetic-private'
    assert config.secrets.threads_user_id == 'synthetic-profile'
    assert 'synthetic-private' not in repr(config) + repr(config.secrets)
    assert redact('synthetic-private synthetic-profile', config.secrets) == '[已隱藏] [已隱藏]'


@pytest.mark.parametrize('setting', ['interval_minutes = 0', 'max_per_day = -1', 'window_start = "25:00"',
                                     'window_end = "08:00"', 'timezone = "nowhere"', 'link_target = "private"',
                                     'sections = ["英文學習"]', 'hashtags = ["bad"]',
                                     'hashtags = ["#一", "#二", "#三"]', 'enabled = "true"'])
def test_config_rejects_invalid_social_values(tmp_path, setting):
    path = tmp_path / 'config.toml'
    path.write_text('[social.threads]\n' + setting + '\n')
    with pytest.raises(ConfigError):
        load_config(path)


def test_delivered_issue_can_backfill_and_never_dry_run_enqueue(issue_directory, social_config, monkeypatch):
    from econ_digest.commands.send import send_digest
    from econ_digest.state import save_state, empty_state
    state = empty_state()
    state['delivered']['2026.10.03'] = {'delivered_at': '2026-10-06T00:00:00+00:00', 'message_count': 1}
    save_state(social_config.paths.data_dir, state)
    config = replace(social_config, telegram=replace(social_config.telegram, delivery='messages'))
    assert send_digest(config, '2026.10.03', dry_run=True) == 0
    assert not Queue(config.paths.data_dir).path.exists()
    assert send_digest(config, '2026.10.03') == 0
    assert len(Queue(config.paths.data_dir).load()['posts']) == 5


def test_enqueue_failure_does_not_undo_delivery(social_config, tmp_path):
    from econ_digest.commands.send import _enqueue_social
    messages = []
    _enqueue_social(social_config, tmp_path, messages.append)
    assert len(messages) == 1 and '本期已傳送' in messages[0]


def test_threads_units_are_configured_and_validated(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    config = tmp_path / 'custom.toml'
    config.write_text('[social.threads]\ninterval_minutes = 17\n')
    guard = tmp_path / 'guard'
    guard.mkdir()
    (guard / 'systemctl').write_text('#!/bin/sh\nexit 99\n')
    (guard / 'systemctl').chmod(0o755)
    target = tmp_path / 'units'
    result = subprocess.run([str(repo / 'deploy/install-threads-timer.sh'), '--config', str(config), '--print-units', str(target)],
                            env={**os.environ, 'PATH': str(guard) + os.pathsep + os.environ['PATH']},
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    service, timer = target / 'econ-digest-threads.service', target / 'econ-digest-threads.timer'
    assert 'social threads post-next' in service.read_text()
    assert '--config "' + str(config) + '"' in service.read_text()
    assert 'OnUnitInactiveSec=17min' in timer.read_text()
    assert 'UMask=0077' in service.read_text()
    analyzer = shutil.which('systemd-analyze')
    if analyzer:
        verified = subprocess.run([analyzer, '--user', 'verify', str(service), str(timer)], capture_output=True, text=True)
        assert verified.returncode == 0, verified.stdout + verified.stderr


def test_preview_uses_frozen_queue_after_digest_changes(issue_directory, social_config, monkeypatch, capsys):
    from econ_digest.models import Digest, load_json, save_json
    monkeypatch.setattr('econ_digest.cli.load_config', lambda _: social_config)
    assert main(['social', 'threads', 'enqueue', '--issue', '2026.10.03']) == 0
    digest = load_json(issue_directory / 'digest.json', Digest)
    digest.classifications['taiwan'].title_zh = '改版後的標題'
    save_json(issue_directory / 'digest.json', digest)
    assert main(['social', 'threads', 'preview', '--issue', '2026.10.03']) == 0
    output = capsys.readouterr().out
    assert '合成taiwan標題' in output
    assert '改版後的標題' not in output
