from dataclasses import replace
from datetime import timedelta
import json
import os
import stat
from urllib.parse import parse_qs

import pytest

from econ_digest.config import Config, SecretsConfig, SocialConfig, ThreadsConfig
from econ_digest.social.client import ThreadsClient, ThreadsError
from econ_digest.social.queue import Queue
from econ_digest.social.scheduler import Scheduler, gate, in_window, planned_schedule
from econ_digest.social.tokens import Token, load_token, store_token, token_path
from .conftest import FakeOpener, Response


def factory(opener):
    return lambda token, user_id, **kwargs: ThreadsClient(token, user_id, opener=opener, **kwargs)


def test_scheduler_posts_at_most_one_then_interval_and_idempotency(social_config, queued, now):
    opener = FakeOpener([Response({'data': [{'quota_usage': 0, 'config': {'quota_total': 250}}]}),
                         Response({'id': 'container'}), Response({'id': 'posted'})])
    waits = []
    scheduler = Scheduler(social_config, clock=lambda: now, client_factory=factory(opener), wait=waits.append)
    assert scheduler.post_next() == 0
    state = queued.load()
    assert state['posts'][0]['post_id'] == 'posted'
    assert state['posts'][0]['container_id'] == 'container'
    assert state['posts'][0]['published_at'] == now.isoformat()
    assert state['posts'][1]['status'] == 'pending'
    assert waits == [30]
    assert scheduler.post_next() == 0
    assert len(opener.requests) == 3
    assert '間隔' in gate(now + timedelta(minutes=59), state, social_config.social.threads)
    assert gate(now + timedelta(minutes=60), state, social_config.social.threads) is None


def test_requeued_earlier_post_is_next_and_keeps_repeated_history(social_config, queued, now):
    state = queued.load()
    first = state['posts'][0]
    first.update(status='posted', post_id='first-publication', container_id='old-container',
                 published_at=(now - timedelta(hours=2)).isoformat())
    state['last_posted_at'] = first['published_at']
    queued.save(state)
    assert queued.requeue(first['post']['key'])
    opener = FakeOpener([Response({'data': [{'quota_usage': 1, 'config': {'quota_total': 250}}]}),
                         Response({'id': 'new-container'}), Response({'id': 'second-publication'})])
    scheduler = Scheduler(social_config, clock=lambda: now, client_factory=factory(opener), wait=lambda _: None)
    assert scheduler.post_next() == 0
    creation = parse_qs(opener.requests[1].data.decode())
    assert creation['text'] == [first['post']['text']]
    assert creation['topic_tag'] == ['經濟學人導讀']
    after = queued.load()
    assert after['posts'][0]['post_id'] == 'second-publication'
    assert after['posts'][0]['container_id'] == 'new-container'
    assert after['posts'][1]['status'] == 'pending'
    assert queued.requeue(first['post']['key'])
    history = queued.load()['posts'][0]['history']
    assert [item['post_id'] for item in history] == ['first-publication', 'second-publication']


def test_requeue_preserves_daily_limit_and_post_interval(social_config, queued, now):
    state = queued.load()
    first = state['posts'][0]
    first.update(status='posted', post_id='old-post', published_at=now.isoformat())
    state['last_posted_at'] = now.isoformat()
    queued.save(state)
    assert queued.requeue(first['post']['key'])
    state = queued.load()
    config = replace(social_config.social.threads, max_per_day=1)
    assert '間隔' in gate(now + timedelta(minutes=59), state, config)
    assert '上限' in gate(now + timedelta(hours=1), state, config)
    assert gate(now + timedelta(days=1), state, config) is None


@pytest.mark.parametrize(('minutes', 'allowed'), [(-1, False), (0, True), (839, True), (840, True), (841, False)])
def test_window_boundaries(now, minutes, allowed):
    assert in_window(now + timedelta(minutes=minutes), ThreadsConfig()) == allowed


def test_overnight_window(now):
    config = ThreadsConfig(window_start='22:00', window_end='08:00')
    assert in_window(now, config)
    assert in_window(now - timedelta(hours=8), config)
    assert not in_window(now + timedelta(hours=1), config)


def test_local_daily_cap_resets_at_midnight(social_config, queued, now):
    state = queued.load()
    state['posts'][0].update(status='posted', published_at=now.isoformat())
    config = replace(social_config.social.threads, max_per_day=1)
    assert '上限' in gate(now + timedelta(hours=1), state, config)
    assert gate(now + timedelta(days=1), state, config) is None


def test_disabled_default_and_dry_run_never_construct_client(social_config, queued, now):
    config = replace(social_config, social=SocialConfig())
    def forbidden(*args, **kwargs):
        pytest.fail('disabled/dry-run must never construct a network client')
    scheduler = Scheduler(config, clock=lambda: now, client_factory=forbidden, alert=forbidden)
    before = queued.path.read_bytes()
    assert scheduler.post_next() == 0
    assert scheduler.post_next(dry_run=True) == 0
    assert queued.path.read_bytes() == before
    assert not token_path(config).exists()
    scheduler = Scheduler(social_config, clock=lambda: now, client_factory=forbidden, alert=forbidden)
    assert scheduler.post_next(dry_run=True) == 0


def test_outside_window_makes_no_requests(social_config, queued, now):
    opener = FakeOpener([])
    assert Scheduler(social_config, clock=lambda: now - timedelta(minutes=1), client_factory=factory(opener)).post_next() == 0
    assert opener.requests == []


def test_retry_after_persists_and_blocks_early_retry(social_config, queued, now):
    opener = FakeOpener([Response({'error': {'code': 4}}, 429, {'Retry-After': '300'})])
    scheduler = Scheduler(social_config, clock=lambda: now, client_factory=factory(opener))
    assert scheduler.post_next() == 1
    assert queued.load()['next_attempt_at'] == (now + timedelta(minutes=5)).isoformat()
    assert scheduler.post_next() == 0
    assert len(opener.requests) == 1


def test_no_remaining_quota_never_creates_container(social_config, queued, now):
    opener = FakeOpener([Response({'data': [{'quota_usage': 250, 'config': {'quota_total': 250}}]})])
    assert Scheduler(social_config, clock=lambda: now, client_factory=factory(opener)).post_next() == 0
    assert len(opener.requests) == 1
    assert queued.load()['posts'][0]['container_id'] is None


def test_authorization_stops_queue_and_alerts_once(social_config, queued, now):
    opener = FakeOpener([Response({'error': {'code': 190, 'message': 'synthetic-private-token'}}, 400)])
    alerts = []
    scheduler = Scheduler(social_config, clock=lambda: now, client_factory=factory(opener), alert=alerts.append)
    assert scheduler.post_next() == 1
    assert scheduler.post_next() == 0
    assert queued.load()['paused']
    assert queued.load()['alerts'] == {'authorization': 'sent'}
    assert len(alerts) == len(opener.requests) == 1
    assert 'THREADS_ACCESS_TOKEN' in alerts[0] and 'synthetic-private-token' not in alerts[0]


@pytest.mark.parametrize('chat_id', ['-100123', '@synthetic-channel', None])
def test_alert_never_targets_a_group_or_channel(social_config, queued, now, monkeypatch, chat_id):
    config = replace(social_config, secrets=replace(social_config.secrets, telegram_chat_id=chat_id,
                                                   telegram_channel_id='@synthetic-channel'))
    def forbidden(*args, **kwargs):
        pytest.fail('must not contact Telegram for a nonprivate destination')
    monkeypatch.setattr('econ_digest.social.scheduler.TelegramClient', forbidden)
    opener = FakeOpener([Response({'error': {'code': 190}}, 400)])
    assert Scheduler(config, clock=lambda: now, client_factory=factory(opener)).post_next() == 1
    assert queued.load()['alerts']['authorization'] == 'unavailable'


def test_private_alert_uses_private_chat_only(social_config, queued, now, monkeypatch):
    sends = []
    class FakeTelegram:
        def __init__(self, token):
            pass
        def send_message_safe(self, chat_id, message):
            sends.append((chat_id, message))
    monkeypatch.setattr('econ_digest.social.scheduler.TelegramClient', FakeTelegram)
    config = replace(social_config, secrets=replace(social_config.secrets, telegram_channel_id='@synthetic-channel'))
    opener = FakeOpener([Response({'error': {'code': 190}}, 400)])
    scheduler = Scheduler(config, clock=lambda: now, client_factory=factory(opener))
    assert scheduler.post_next() == 1
    assert scheduler.post_next() == 0
    assert len(sends) == 1 and sends[0][0] == '12345'


def test_token_refresh_storage_permissions_and_no_log(social_config, queued, now, capsys, caplog):
    config = replace(social_config, secrets=replace(social_config.secrets,
                                                   threads_token_issued_at=(now - timedelta(days=51)).isoformat()))
    opener = FakeOpener([Response({'access_token': 'synthetic-refreshed-token', 'expires_in': 5184000}),
                         Response({'data': [{'quota_usage': 0, 'config': {'quota_total': 250}}]}),
                         Response({'id': 'container'}), Response({'id': 'posted'})])
    scheduler = Scheduler(config, clock=lambda: now, client_factory=factory(opener), wait=lambda _: None)
    assert scheduler.post_next() == 0
    stored = load_token(config, now)
    assert stored.access_token == 'synthetic-refreshed-token'
    assert stored.age_days(now) == 0
    assert stat.S_IMODE(token_path(config).stat().st_mode) == 0o600
    assert 'synthetic-refreshed-token' not in repr(stored)
    assert 'synthetic-refreshed-token' not in capsys.readouterr().out + caplog.text
    assert 'synthetic-private-token' not in caplog.text


def test_refresh_failure_alert_with_renewal_instructions(social_config, queued, now):
    config = replace(social_config, secrets=replace(social_config.secrets,
                                                   threads_token_issued_at=(now - timedelta(days=51)).isoformat()))
    opener = FakeOpener([Response({'error': {'code': 190}}, 400)])
    alerts = []
    scheduler = Scheduler(config, clock=lambda: now, client_factory=factory(opener), alert=alerts.append)
    assert scheduler.post_next() == 1
    assert scheduler.post_next() == 0
    assert len(alerts) == 1
    assert 'threads_basic' in alerts[0] and '長期權杖' in alerts[0]
    assert queued.load()['paused']


def test_newer_cached_token_and_environment_rotation(social_config, now):
    initial = load_token(social_config, now)
    newer = replace(initial, access_token='refreshed-private', issued_at=now + timedelta(days=1))
    store_token(social_config, newer)
    assert load_token(social_config, now + timedelta(days=1)).access_token == 'refreshed-private'
    config = replace(social_config, secrets=replace(social_config.secrets, threads_access_token='new-env-private',
                                                   threads_token_issued_at=(now + timedelta(days=2)).isoformat()))
    assert load_token(config, now + timedelta(days=2)).access_token == 'new-env-private'
    assert load_token(social_config, now + timedelta(days=2)).access_token == 'refreshed-private'


def test_initial_age_uses_private_env_timestamp(social_config, now, monkeypatch, tmp_path):
    env = tmp_path / 'private-env'
    env.write_text('THREADS_ACCESS_TOKEN=synthetic\n')
    stamp = (now - timedelta(days=5)).timestamp()
    os.utime(env, (stamp, stamp))
    monkeypatch.setenv('ECON_DIGEST_ENV_FILE', str(env))
    config = replace(social_config, secrets=replace(social_config.secrets, threads_token_issued_at=None))
    token = load_token(config, now)
    assert token.age_estimated and token.age_days(now) == 5
    store_token(config, token)
    assert load_token(config, now + timedelta(days=1)).age_days(now + timedelta(days=1)) == 6


def test_resume_container_after_crash_without_recreation(social_config, queued, now):
    state = queued.load()
    state['posts'][0].update(container_id='saved-container', status='container', created_at=now.isoformat())
    queued.save(state)
    opener = FakeOpener([Response({'data': [{'quota_usage': 0, 'config': {'quota_total': 250}}]}),
                         Response({'status': 'FINISHED'}), Response({'id': 'posted'})])
    assert Scheduler(social_config, clock=lambda: now, client_factory=factory(opener)).post_next() == 0
    assert queued.load()['posts'][0]['container_id'] == 'saved-container'
    assert [r.method for r in opener.requests] == ['GET', 'GET', 'POST']


def test_lost_publish_response_is_recovered_not_republished(social_config, queued, now):
    state = queued.load()
    record = state['posts'][0]
    record.update(container_id='container', status='publishing', publish_started_at=now.isoformat())
    queued.save(state)
    opener = FakeOpener([Response({'data': [{'quota_usage': 1, 'config': {'quota_total': 250}}]}),
                         Response({'status': 'PUBLISHED'}),
                         Response({'data': [{'id': 'already-posted', 'text': record['post']['text'], 'timestamp': now.isoformat()}]})])
    assert Scheduler(social_config, clock=lambda: now, client_factory=factory(opener)).post_next() == 0
    assert queued.load()['posts'][0]['post_id'] == 'already-posted'
    assert all(r.method == 'GET' for r in opener.requests)


def test_unrecoverable_publish_pauses_instead_of_duplicate(social_config, queued, now):
    state = queued.load()
    state['posts'][0].update(container_id='container', status='publishing', publish_started_at=now.isoformat())
    queued.save(state)
    opener = FakeOpener([Response({'data': [{'quota_usage': 1, 'config': {'quota_total': 250}}]}),
                         Response({'status': 'PUBLISHED'}), Response({'data': []})])
    alerts = []
    assert Scheduler(social_config, clock=lambda: now, client_factory=factory(opener), alert=alerts.append).post_next() == 1
    assert queued.load()['paused'] and queued.load()['posts'][0]['status'] == 'uncertain'
    assert len(alerts) == 1 and all(r.method == 'GET' for r in opener.requests)


def test_schedule_default_limit_and_window(now):
    schedule = planned_schedule(now, 66, ThreadsConfig())
    assert len(schedule) == 66
    assert schedule[0] == now and schedule[14] == now + timedelta(hours=14)
    assert schedule[15] == now + timedelta(days=1)
    assert schedule[-1] == now + timedelta(days=4, hours=5)


def test_token_refresh_runs_even_when_queue_is_empty(social_config, now):
    config = replace(social_config, secrets=replace(social_config.secrets,
                                                   threads_token_issued_at=(now - timedelta(days=51)).isoformat()))
    opener = FakeOpener([Response({'access_token': 'synthetic-refreshed', 'expires_in': 5184000})])
    scheduler = Scheduler(config, clock=lambda: now, client_factory=factory(opener))
    assert scheduler.post_next() == 0
    assert load_token(config, now).access_token == 'synthetic-refreshed'
    assert len(opener.requests) == 1


def test_token_metadata_rejects_future_and_partial_credentials(social_config, now):
    from econ_digest.state import StateError
    partial = replace(social_config, secrets=replace(social_config.secrets, threads_user_id=None))
    with pytest.raises(StateError):
        load_token(partial, now)
    future = replace(social_config, secrets=replace(social_config.secrets,
                                                   threads_token_issued_at=(now + timedelta(days=1)).isoformat()))
    with pytest.raises(StateError):
        load_token(future, now)


def test_ambiguous_publish_uses_status_check_before_retry(social_config, queued, now):
    from urllib.error import URLError
    opener = FakeOpener([Response({'data': [{'quota_usage': 0, 'config': {'quota_total': 250}}]}),
                         Response({'id': 'container'}), URLError('synthetic-private-token'),
                         Response({'data': [{'quota_usage': 1, 'config': {'quota_total': 250}}]}),
                         Response({'status': 'PUBLISHED'}),
                         Response({'data': [{'id': 'posted', 'text': queued.load()['posts'][0]['post']['text'], 'timestamp': now.isoformat()}]})])
    cursor = [now]
    scheduler = Scheduler(social_config, clock=lambda: cursor[0], client_factory=factory(opener), wait=lambda _: None)
    assert scheduler.post_next() == 1
    assert queued.load()['posts'][0]['status'] == 'publishing'
    cursor[0] += timedelta(minutes=1)
    assert scheduler.post_next() == 0
    assert queued.load()['posts'][0]['post_id'] == 'posted'
    assert sum(r.full_url.endswith('/threads_publish') for r in opener.requests) == 1


def test_expired_publish_attempt_is_never_recreated(social_config, queued, now):
    state = queued.load()
    state['posts'][0].update(container_id='expired', status='publishing', publish_started_at=now.isoformat())
    queued.save(state)
    opener = FakeOpener([Response({'data': [{'quota_usage': 0, 'config': {'quota_total': 250}}]}), Response({'status': 'EXPIRED'})])
    alerts = []
    assert Scheduler(social_config, clock=lambda: now, client_factory=factory(opener), alert=alerts.append).post_next() == 1
    assert queued.load()['paused']
    assert all(r.method == 'GET' for r in opener.requests)


def test_account_change_never_posts_under_new_identity(social_config, queued, now):
    import hashlib
    state = queued.load()
    state['account_hash'] = hashlib.sha256(b'different-synthetic-account').hexdigest()
    queued.save(state)
    opener = FakeOpener([])
    alerts = []
    assert Scheduler(social_config, clock=lambda: now, client_factory=factory(opener), alert=alerts.append).post_next() == 1
    assert queued.load()['paused'] and opener.requests == []
