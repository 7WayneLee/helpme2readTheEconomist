from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from econ_digest.social.client import ThreadsClient, ThreadsError, retry_after_seconds
from .conftest import FakeOpener, Response


def test_two_step_text_publication(post, now):
    opener = FakeOpener([Response({'id': 'container'}), Response({'id': 'posted'})])
    client = ThreadsClient('synthetic-token', 'synthetic-user', opener=opener, clock=lambda: now)
    container = client.create_container(post)
    assert client.publish_container(container) == 'posted'
    create, publish = opener.requests
    assert create.method == publish.method == 'POST'
    assert create.full_url.endswith('/v1.0/synthetic-user/threads')
    params = parse_qs(create.data.decode())
    assert params['media_type'] == ['TEXT']
    assert params['text'] == [post.text]
    assert params['topic_tag'] == ['經濟學人導讀']
    assert '#' not in params['text'][0]
    assert params['link_attachment'] == [post.link_url]
    assert parse_qs(publish.data.decode())['creation_id'] == ['container']
    assert 'synthetic-token' not in repr(client)


def test_intro_image_does_not_send_unsupported_link_attachment(post):
    opener = FakeOpener([Response({'id': 'container'})])
    client = ThreadsClient('synthetic-token', 'synthetic-user', opener=opener)
    client.create_container(replace(post, image_url='https://example.invalid/cover.jpg'))
    params = parse_qs(opener.requests[0].data.decode())
    assert params['media_type'] == ['IMAGE']
    assert params['image_url'] == ['https://example.invalid/cover.jpg']
    assert params['topic_tag'] == ['經濟學人導讀']
    assert '#' not in params['text'][0]
    assert 'link_attachment' not in params
    assert post.link_url in params['text'][0]


@pytest.mark.parametrize('image_url', [None, 'https://example.invalid/cover.jpg'])
def test_empty_topic_is_omitted_for_text_and_image(post, image_url):
    opener = FakeOpener([Response({'id': 'container'})])
    client = ThreadsClient('synthetic-token', 'synthetic-user', opener=opener)
    client.create_container(replace(post, image_url=image_url, topic_tag=''))
    assert 'topic_tag' not in parse_qs(opener.requests[0].data.decode(), keep_blank_values=True)


def test_quota_uses_endpoint_config_not_assumed_ceiling(now):
    opener = FakeOpener([Response({'data': [{'quota_usage': 7, 'config': {'quota_total': 10}}]})])
    client = ThreadsClient('synthetic-token', 'synthetic-user', opener=opener, clock=lambda: now)
    assert client.remaining_quota() == 3
    assert '/threads_publishing_limit?' in opener.requests[0].full_url
    assert parse_qs(urlsplit(opener.requests[0].full_url).query)['fields'] == ['quota_usage,config']


@pytest.mark.parametrize('data', [{}, {'data': []}, {'data': [{'quota_usage': '0', 'config': {'quota_total': 250}}]}])
def test_quota_malformed_fails_closed(data):
    client = ThreadsClient('synthetic-token', 'synthetic-user', opener=FakeOpener([Response(data)]))
    with pytest.raises(ThreadsError):
        client.remaining_quota()


def test_retry_after_http_error_is_sanitized(post, now):
    error = HTTPError('https://example.invalid/secret-token', 429, 'secret-token', {'Retry-After': '120'},
                      BytesIO(b'{"error":{"message":"secret-token synthetic-user","code":4}}'))
    client = ThreadsClient('secret-token', 'synthetic-user', opener=FakeOpener([error]), clock=lambda: now)
    with pytest.raises(ThreadsError) as result:
        client.create_container(post)
    assert result.value.retry_after == 120
    assert result.value.authorization is False
    assert 'secret-token' not in str(result.value)
    assert 'synthetic-user' not in str(result.value)


@pytest.mark.parametrize('status,code', [(401, None), (403, None), (400, 190), (400, 10), (200, 200)])
def test_authorization_failures(status, code):
    client = ThreadsClient('synthetic-token', 'synthetic-user', opener=FakeOpener([
        Response({'error': {'code': code, 'message': 'synthetic-token'}}, status=status)]))
    with pytest.raises(ThreadsError) as result:
        client.remaining_quota()
    assert result.value.authorization
    assert 'synthetic-token' not in str(result.value)


def test_network_publish_error_is_ambiguous(post):
    client = ThreadsClient('synthetic-token', 'synthetic-user', opener=FakeOpener([URLError('synthetic-token')]))
    with pytest.raises(ThreadsError) as result:
        client.publish_container('container')
    assert result.value.ambiguous
    assert 'synthetic-token' not in str(result.value)


def test_retry_after_dates(now):
    assert retry_after_seconds('Tue, 06 Oct 2026 00:05:00 GMT', now) == 300
    assert retry_after_seconds('bad', now) is None
    assert retry_after_seconds('nan', now) is None
    assert retry_after_seconds('-1', now) == 0


def test_refresh_endpoint(now):
    opener = FakeOpener([Response({'access_token': 'synthetic-new', 'expires_in': 5184000})])
    client = ThreadsClient('synthetic-old', 'synthetic-user', opener=opener, clock=lambda: now)
    assert client.refresh_token() == ('synthetic-new', 5184000)
    req = opener.requests[0]
    assert req.full_url.startswith('https://graph.threads.net/refresh_access_token?')
    assert parse_qs(urlsplit(req.full_url).query)['grant_type'] == ['th_refresh_token']


def test_published_response_recovery(post, now):
    opener = FakeOpener([Response({'data': [{'id': 'posted', 'text': post.text, 'timestamp': now.isoformat()}]})])
    client = ThreadsClient('synthetic-token', 'synthetic-user', opener=opener)
    assert client.find_published(post, now - timedelta(seconds=1)) == ('posted', now.isoformat())
