from __future__ import annotations

import io
import json
from datetime import date, datetime, timezone
from email.message import Message
from email.utils import format_datetime
from pathlib import Path
from urllib.error import HTTPError

import pytest

from econ_digest.research.cna import CNAClient, parse_article, parse_search, url_date


def search_html(items: list[tuple[str, str]], quote: str = "'") -> str:
    objects = [{'@type': 'BreadcrumbList', 'itemListElement': []},
               {'@type': 'ItemList', 'itemListElement': [
                   {'@type': 'ListItem', 'position': i, 'name': name, 'url': url}
                   for i, (name, url) in enumerate(items, 1)]}]
    return ''.join(f'<script type={quote}application/ld+json{quote}>{json.dumps(obj)}</script>' for obj in objects)


@pytest.mark.parametrize('quote', ["'", '"'])
def test_jsonld_itemlist_single_or_double_quotes_and_url_dates(quote: str) -> None:
    html = search_html([('合成新報導', '/news/ait/202610010123.aspx'),
                        ('合成舊報導', '/news/aipl/202409290001.aspx'),
                        ('重複', '/news/ait/202610010123.aspx'),
                        ('非中央社', 'https://example.invalid/news/ait/202610010123.aspx')], quote)
    results = parse_search(html, today=date(2026, 10, 5))
    assert len(results) == 1
    assert results[0].date == '2026-10-01' and results[0].title == '合成新報導'
    assert results[0].url == 'https://www.cna.com.tw/news/ait/202610010123.aspx'


@pytest.mark.parametrize('url, expected', [
    ('https://www.cna.com.tw/news/ait/202610010123.aspx', date(2026, 10, 1)),
    ('https://www.cna.com.tw/news/afe/202602300001.aspx', None),
    ('https://www.cna.com.tw/search/hysearchws.aspx?q=20261001', None),
])
def test_date_from_article_path(url: str, expected: date | None) -> None:
    assert url_date(url) == expected


def test_nested_graph_bad_scripts_limit_and_old_only_results() -> None:
    html = '<script type="application/ld+json">invalid</script>'
    html += '<script TYPE="application/ld+json">' + json.dumps({'@graph': [
        {'@type': 'ItemList', 'itemListElement': [
            {'item': {'name': f'合成{i}', 'url': f'/news/aipl/2024100{i}0001.aspx'}} for i in range(1, 8)]}]}) + '</script>'
    assert len(parse_search(html, today=date(2026, 10, 5))) == 5
    assert parse_search(html, today=date(2026, 10, 5))[0].date == '2024-10-07'
    future = search_html([('未來日期', '/news/aipl/202610060001.aspx')])
    assert parse_search(future, today=date(2026, 10, 5)) == []


def test_excerpt_uses_first_two_body_paragraphs_and_200_character_cap() -> None:
    html = '<h1>合成標題<span>附加字</span></h1><p>選單</p><div class="paragraph"><p>合成首段<b>內容</b>。</p><p>合成次段。</p><p>第三段不要。</p></div>'
    title, excerpt = parse_article(html)
    assert title == '合成標題附加字'
    assert excerpt == '合成首段內容。\n合成次段。'
    assert len(parse_article('<div itemprop="articleBody"><p>' + '合' * 220 + '</p></div>')[1]) == 200


def test_politeness_cache_dedup_and_expiry(tmp_path: Path) -> None:
    calls, sleeps = [], []
    clock = [0.0]
    wall = [100.0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    def opener(request, timeout):
        calls.append(request.full_url)
        assert timeout == 15 and 'econ-digest' in request.get_header('User-agent')
        if '/search/' in request.full_url:
            return io.BytesIO(search_html([('合成', '/news/aipl/202610010001.aspx')]).encode())
        return io.BytesIO('<h1>合成內文標題</h1><div class="paragraph"><p>合成摘錄。</p></div>'.encode())

    client = CNAClient(tmp_path, opener=opener, sleep=sleep, clock=lambda: clock[0],
                       wall_clock=lambda: wall[0], today=date(2026, 10, 5))
    evidence = client.retrieve(['台灣', '合成'])
    assert len(calls) == 3 and sleeps == [2.5, 2.5]
    assert len(evidence) == 1 and evidence[0].excerpt == '合成摘錄。'
    assert evidence[0].source.title == '合成內文標題'
    assert client.retrieve(['台灣', '合成']) == evidence and len(calls) == 3
    wall[0] += 7 * 86400 + 1
    client.retrieve(['台灣'])
    assert len(calls) == 4  # Search expired, article excerpt still cached.
    assert all('paragraph' not in path.read_text() for path in tmp_path.glob('*.json'))


def test_unreachable_cna_records_warning_signal_and_invalid_cache_retries(tmp_path: Path) -> None:
    def opener(*args, **kwargs):
        raise OSError('synthetic unavailable')

    client = CNAClient(tmp_path, opener=opener, sleep=lambda _: None)
    assert client.retrieve(['台灣']) == []
    assert client.errors == ['OSError']


def test_corrupt_search_cache_is_refetched(tmp_path: Path) -> None:
    calls = []
    def opener(request, **kwargs):
        calls.append(request.full_url)
        return io.BytesIO(search_html([('合成', '/news/aipl/202610010001.aspx')]).encode())
    client = CNAClient(tmp_path, opener=opener, sleep=lambda _: None, today=date(2026, 10, 5))
    first = client.search('台灣')
    next(tmp_path.glob('*.json')).write_text('{broken')
    assert client.search('台灣') == first and len(calls) == 2


@pytest.mark.parametrize('status', [429, 503])
@pytest.mark.parametrize('retry_after', ['7', 'http-date', 'invalid'])
def test_retry_after_and_rate_limit_recovery(tmp_path, status, retry_after):
    clock, calls, sleeps = [0.0], [], []
    wall = 1_000_000.0
    headers = Message()
    headers['Retry-After'] = (format_datetime(datetime.fromtimestamp(wall + 7, timezone.utc), usegmt=True)
                              if retry_after == 'http-date' else retry_after)
    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    def opener(request, **kwargs):
        calls.append(clock[0])
        if len(calls) == 1:
            raise HTTPError(request.full_url, status, 'synthetic rate limit', headers, None)
        return io.BytesIO(search_html([('合成', '/news/aipl/202610010001.aspx')]).encode())
    client = CNAClient(tmp_path, opener=opener, clock=lambda: clock[0], sleep=sleep,
                       wall_clock=lambda: wall, today=date(2026, 10, 5))
    assert len(client.search('合成')) == 1
    assert sleeps == [2.5 if retry_after == 'invalid' else 7.0]
    assert client.request_count == 2 and client.errors == []


def test_exponential_backoff_stops_after_three_retries(tmp_path):
    clock, calls, sleeps = [0.0], [], []
    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    def opener(request, **kwargs):
        calls.append(clock[0])
        raise HTTPError(request.full_url, 429, 'synthetic rate limit', Message(), None)
    client = CNAClient(tmp_path, opener=opener, clock=lambda: clock[0], sleep=sleep)
    assert client.search('合成') == []
    assert len(calls) == client.request_count == 4
    assert sleeps == [2.5, 5.0, 10.0] and client.errors == ['HTTPError:429']
    assert list(tmp_path.glob('*.json')) == []


def test_budget_exhaustion_counts_retries_warns_once_and_allows_cache(tmp_path, caplog):
    clock, calls = [0.0], []
    def opener(request, **kwargs):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 503, 'synthetic busy', Message(), None)
        return io.BytesIO(search_html([('合成', '/news/aipl/202610010001.aspx')]).encode())
    client = CNAClient(tmp_path, opener=opener, clock=lambda: clock[0],
                       sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
                       today=date(2026, 10, 5), request_budget=2)
    first = client.search('台灣')
    assert first
    assert client.retrieve(['台灣', '另一查詢']) == []
    assert client.search('其他查詢') == [] and client.search('台灣') == first
    assert len(calls) == client.request_count == 2
    assert client.errors == ['request_budget'] and len(client.warnings) == 1
    assert '請求上限（2 次）' in caplog.text


def test_cache_survives_new_clients_search_seven_days_articles_thirty(tmp_path):
    calls, wall = [], [100.0]
    def opener(request, **kwargs):
        calls.append(request.full_url)
        html = (search_html([('合成', '/news/aipl/202610010001.aspx')]) if '/search/' in request.full_url
                else '<h1>合成</h1><div class="paragraph"><p>合成摘錄。</p></div>')
        return io.BytesIO(html.encode())
    def client(budget=40):
        return CNAClient(tmp_path, opener=opener, sleep=lambda _: None, wall_clock=lambda: wall[0],
                          today=date(2026, 10, 5), request_budget=budget)
    first = client().retrieve(['台灣'])
    wall[0] += 6 * 86400
    warm = client(0)
    assert warm.retrieve(['台灣']) == first and warm.request_count == 0 and warm.warnings == []
    wall[0] = 100 + 7 * 86400
    assert client().retrieve(['台灣']) == first and len(calls) == 3
    wall[0] = 100 + 29 * 86400
    assert client().retrieve(['台灣']) == first and len(calls) == 4
    wall[0] = 100 + 30 * 86400
    assert client().retrieve(['台灣']) == first and len(calls) == 5
    assert '/news/' in calls[-1]


def test_search_only_evidence_never_fetches_pages(tmp_path):
    calls = []
    def opener(request, **kwargs):
        calls.append(request.full_url)
        assert '/search/' in request.full_url
        return io.BytesIO(search_html([('合成標題', '/news/aipl/202610010001.aspx')]).encode())
    client = CNAClient(tmp_path, opener=opener, sleep=lambda _: None, today=date(2026, 10, 5))
    result = client.retrieve_search(['台灣', '合成'])
    assert len(calls) == 2 and len(result) == 1
    assert result[0].excerpt == result[0].source.title == '合成標題'
