from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path

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
    assert len(calls) == 3 and sleeps == [1.0, 1.0]
    assert len(evidence) == 1 and evidence[0].excerpt == '合成摘錄。'
    assert evidence[0].source.title == '合成內文標題'
    assert client.retrieve(['台灣', '合成']) == evidence and len(calls) == 3
    wall[0] += 86401
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
