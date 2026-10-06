from __future__ import annotations

import io
import json
import ssl
from dataclasses import replace
from datetime import date
from email.message import Message
from email.utils import formatdate
from pathlib import Path
from urllib.error import HTTPError

import pytest

from econ_digest.config import ResearchConfig, load_config
from econ_digest.models import Source
from econ_digest.research.cna import CNAClient, Evidence
from econ_digest.research.client import ResearchClient, merge_evidence
from econ_digest.research.domestic import DomesticAdapter
from econ_digest.research.government import GovernmentAdapter, parse_cec
from econ_digest.research.http import Fetcher, government_ssl_context
from econ_digest.research.parsers import parse_article, parse_html_list, parse_rss, recent
from econ_digest.research.rss import RSSAdapter, keywords
from econ_digest.research.sources import DOMESTIC, GOVERNMENT, INTERNATIONAL

DAY = date(2026, 10, 3)


def feed(url='https://www.bbc.com/news/articles/synthetic', title='Taiwan synthetic crisis', published='Fri, 02 Oct 2026 09:00:00 GMT'):
    return f'<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>{published}</pubDate><description>&lt;p&gt;Taiwan synthetic evidence.&lt;/p&gt;</description></item></channel></rss>'


@pytest.mark.parametrize('site', INTERNATIONAL)
def test_each_international_feed_parses_own_synthetic_item(site):
    hosts = {'bbc_asia': 'www.bbc.com', 'bbc_zh': 'www.bbc.com', 'dw': 'www.dw.com', 'rfi': 'www.rfi.fr', 'guardian': 'www.theguardian.com'}
    url = f'https://{hosts[site.key]}/synthetic'
    result = parse_rss(feed(url), site.outlet, site.url)
    assert len(result) == 1
    assert result[0].source == Source(site.outlet, '2026-10-02', 'Taiwan synthetic crisis', url)
    assert result[0].excerpt == 'Taiwan synthetic evidence.'


def test_rdf_atom_short_excerpt_and_invalid_dates():
    rdf = '<rdf:RDF xmlns:rdf="urn:rdf" xmlns:dc="urn:dc"><item><title>合成臺灣</title><link>https://www.dw.com/zh/synthetic</link><dc:date>2026-10-01T08:00:00Z</dc:date><description>' + '合' * 220 + '</description></item></rdf:RDF>'
    assert len(parse_rss(rdf, 'DW 中文', '')[0].excerpt) == 200
    atom = '<feed xmlns="urn:atom"><entry><title>合成</title><link href="https://www.bbc.com/synthetic"/><updated>2026-10-01</updated><summary>摘錄</summary></entry></feed>'
    assert parse_rss(atom, 'BBC', '')[0].source.date == '2026-10-01'
    assert parse_rss(feed(published='bad date'), 'BBC', '') == []
    assert parse_rss(feed(url='https://reuters.com/synthetic'), 'BBC', '') == []


@pytest.mark.parametrize('site, path', [(DOMESTIC[0], '/article/123'), (DOMESTIC[1], '/news/story/1/123'), (DOMESTIC[2], 'https://news.ltn.com.tw/news/politics/breakingnews/123')])
def test_each_domestic_search_parses_synthetic_dated_card(site, path):
    base = site.url.format(query='synthetic')
    body = f'<ul><li><time datetime="2026-10-01">10月1日</time><a href="{path}" title="合成台灣標題">合成台灣標題</a></li></ul>'
    result = parse_html_list(body, site.outlet, base)
    assert result[0].source.date == '2026-10-01'
    assert result[0].source.title == result[0].excerpt == '合成台灣標題'
    assert result[0].source.url.startswith('https://')


@pytest.mark.parametrize('site, path', [(GOVERNMENT[0], 'News_Content.aspx?n=95&s=1'), (GOVERNMENT[1], 'news/pressrelease/123'), (GOVERNMENT[2], 'news/plaact/123'), (GOVERNMENT[3], '/NEWS/123'), (GOVERNMENT[4], '/Page/ABC/123-abc'), (GOVERNMENT[5], 'News_Content.aspx?n=3703&s=1'), (GOVERNMENT[6], '/central/article/123')])
def test_each_government_list_parses_roc_date_and_own_url(site, path):
    body = f'<base href="/"><table><tr><td>115年10月01日</td><td><a href="{path}" title="合成已公布數據">合成已公布數據</a></td></tr></table>'
    result = parse_html_list(body, site.outlet, site.url)
    assert len(result) == 1
    assert result[0].source.date == '2026-10-01'
    assert result[0].source.title == result[0].excerpt == '合成已公布數據'
    assert '/news/news/' not in result[0].source.url


def test_cec_nuxt_synthetic_payload_and_article_date_metadata():
    payload = [{'articleId': 1, 'title': 2, 'beginTime': 3}, '123', '合成正式公告', '20261001153000']
    result = parse_cec('<script id="__NUXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>', '')
    assert result[0].source.url == 'https://www.cec.gov.tw/central/article/123'
    assert result[0].source.date == '2026-10-01'
    title, excerpt, published = parse_article('<h1>合成新聞</h1><meta property="article:published_time" content="2026-10-01T12:00:00+08:00"><meta name="description" content="合成摘錄">')
    assert (title, excerpt, published) == ('合成新聞', '合成摘錄', date(2026, 10, 1))


@pytest.mark.parametrize('days', [14, 365])
def test_recency_boundaries_and_future_dates(days):
    from datetime import timedelta
    entries = [Evidence('', Source('BBC', (DAY + timedelta(days=offset)).isoformat(), '合成', 'https://www.bbc.com/synthetic'), '') for offset in [0, -days, -days-1, 1]]
    assert [e.source.date for e in recent(entries, DAY, days)] == [DAY.isoformat(), (DAY-timedelta(days=days)).isoformat()]


def test_spacing_is_per_host_and_budget_is_shared_including_retries(tmp_path):
    clock, calls, sleeps = [0.0], [], []
    def sleep(seconds): sleeps.append(seconds); clock[0] += seconds
    def opener(request, **kwargs):
        calls.append((request.full_url, clock[0]))
        assert kwargs['timeout'] == 15
        assert 'econ-digest' in request.get_header('User-agent')
        return io.BytesIO(b'ok')
    f = Fetcher(tmp_path, request_budget=3, opener=opener, clock=lambda: clock[0], sleep=sleep)
    assert f.fetch('https://udn.com/a') == 'ok'
    assert f.fetch('https://news.pts.org.tw/a') == 'ok'
    assert f.fetch('https://udn.com/b') == 'ok'
    assert f.fetch('https://news.pts.org.tw/b') is None
    assert sleeps == [2.5] and f.request_count == 3
    assert len(f.warnings) == 1


@pytest.mark.parametrize('status', [429, 503])
@pytest.mark.parametrize('retry_after', ['7', 'http-date', 'invalid'])
def test_shared_retry_after(tmp_path, status, retry_after):
    clock, calls, sleeps = [0.0], [], []
    headers = Message(); headers['Retry-After'] = formatdate(1007, usegmt=True) if retry_after == 'http-date' else retry_after
    def sleep(seconds): sleeps.append(seconds); clock[0] += seconds
    def opener(request, **kwargs):
        calls.append(request.full_url)
        if len(calls) == 1: raise HTTPError(request.full_url, status, '', headers, None)
        return io.BytesIO(b'ok')
    f = Fetcher(tmp_path, opener=opener, clock=lambda: clock[0], wall_clock=lambda: 1000, sleep=sleep)
    assert f.fetch('https://udn.com/synthetic') == 'ok'
    assert sleeps == [2.5 if retry_after == 'invalid' else 7]
    assert f.request_count == 2 and not f.errors


def test_cache_ttl_and_once_per_run(tmp_path):
    wall, calls = [100.0], []
    def opener(request, **kwargs): calls.append(request.full_url); return io.BytesIO(b'[]')
    def client(): return Fetcher(tmp_path, opener=opener, sleep=lambda _: None, wall_clock=lambda: wall[0])
    assert client().cached('https://udn.com/rss', 'rss', json.loads) == []
    wall[0] += 6*3600 - 1
    assert client().cached('https://udn.com/rss', 'rss', json.loads) == [] and len(calls) == 1
    wall[0] += 1
    f = client(); f.cached('https://udn.com/rss', 'rss', json.loads, once=True)
    wall[0] += 6*3600
    f.cached('https://udn.com/rss', 'rss', json.loads, once=True)
    assert len(calls) == 2


def test_robots_disallow_falls_back_to_rss_and_logs(tmp_path, caplog):
    calls = []
    site = DOMESTIC[0]
    def opener(request, **kwargs):
        calls.append(request.full_url)
        if request.full_url.endswith('robots.txt'): return io.BytesIO(b'User-agent: *\nDisallow: /search/\n')
        assert request.full_url == site.rss
        return io.BytesIO(feed('https://news.pts.org.tw/article/123', '合成台海熱線').encode())
    caplog.set_level('INFO')
    f = Fetcher(tmp_path, opener=opener, sleep=lambda _: None)
    adapter = DomesticAdapter(site, f, DAY)
    assert len(adapter.retrieve(['台海 熱線'])) == 1
    assert len(adapter.retrieve(['台海 熱線'])) == 1 and len(calls) == 2
    assert 'RSS' in caplog.text and list(f.robots_decisions.values()) == [False]


def test_undated_ltn_hit_requires_article_metadata(tmp_path):
    site = DOMESTIC[2]
    def opener(request, **kwargs):
        if request.full_url.endswith('robots.txt'): return io.BytesIO(b'User-agent: *\nAllow: /\n')
        if 'search.ltn' in request.full_url: return io.BytesIO(b'<li><a href="https://news.ltn.com.tw/news/politics/breakingnews/123" title="Synthetic news">Synthetic news</a><span>5 minutes ago</span></li>')
        return io.BytesIO(b'<meta property="article:published_time" content="2026-10-02"><meta property="og:title" content="Synthetic news"><meta name="description" content="Synthetic excerpt">')
    f = Fetcher(tmp_path, opener=opener, sleep=lambda _: None)
    result = DomesticAdapter(site, f, DAY).retrieve(['合成'])
    assert result[0].source.date == '2026-10-02' and result[0].excerpt == 'Synthetic excerpt'


def test_rss_matching_english_keywords_top_three_and_feed_once(tmp_path):
    calls = []
    def opener(request, **kwargs):
        calls.append(request.full_url)
        body = '<rss><channel>' + ''.join(feed(title=f'Taiwan AI synthetic crisis {i}').split('<channel>')[1].split('</channel>')[0].replace('/synthetic', f'/synthetic{i}') for i in range(5)) + '</channel></rss>'
        return io.BytesIO(body.encode())
    f = Fetcher(tmp_path, opener=opener)
    adapter = RSSAdapter(INTERNATIONAL[0], f, DAY)
    assert len(adapter.retrieve(keywords(['台灣'], 'An AI crisis', 'Diplomacy', ['Taiwan']))) == 3
    adapter.retrieve(keywords(['中國'], 'China crisis'))
    assert len(calls) == 1


def test_ssl_context_loads_verified_public_bundle():
    context = government_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert any('TWCA Secure SSL Certification Authority' in str(cert['subject']) for cert in context.get_ca_certs())


def test_merge_dedupe_diversity_cap_and_unique_ids():
    def ev(i, title, outlet='中央社'): return Evidence('cna1', Source(outlet, '2026-10-01', title, f'https://www.cna.com.tw/news/aipl/20261001{i:04}.aspx'), '摘' * 250)
    groups = [[ev(i, f'合成完全不同標題第{i}條甲乙丙丁') for i in range(20)], [ev(40, '合成完全不同標題第0條甲乙丙丁。', '公視'), ev(41, '公視獨有合成報導', '公視')]]
    result = merge_evidence(groups)
    assert len(result) <= 12 and len({e.id for e in result}) == len(result)
    assert sum(e.source.title.startswith('合成完全不同標題第0條') for e in result) == 1
    assert any(e.source.outlet == '公視' for e in result)
    assert all(len(e.excerpt) == 200 for e in result)


def test_cna_budget_alias_and_per_source_configuration(tmp_path):
    path = tmp_path/'config.toml'
    path.write_text('[research]\ncna_request_budget = 9\npts = false\nudn = false\nltn = false\n')
    settings = load_config(path).research
    assert settings.request_budget == settings.cna_request_budget == 9
    assert not settings.pts and settings.bbc_asia
    path.write_text('[research]\ncna_request_budget = 9\nrequest_budget = 120\n')
    assert load_config(path).research.request_budget == 120
    assert ResearchConfig().request_budget == 120


def test_shared_analysis_budget_counts_cna_and_other_sources(tmp_path):
    calls = []
    def opener(request, **kwargs):
        calls.append(request.full_url)
        if request.full_url.endswith('robots.txt'): return io.BytesIO(b'User-agent: *\nAllow: /\n')
        if '/search/' in request.full_url: return io.BytesIO(b'<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"name":"Synthetic evidence","url":"/news/aipl/202610010001.aspx"}]}</script>')
        return io.BytesIO(b'<h1>Synthetic evidence</h1><div class="paragraph"><p>Synthetic excerpt.</p></div>')
    cna = CNAClient(tmp_path, opener=opener, sleep=lambda _: None, today=DAY)
    client = ResearchClient(cna, ResearchConfig(request_budget=3), '2026.10.03')
    assert client._cna(['合成'])
    client.government[0].latest()
    assert len(calls) == client.fetcher.request_count == 3
    assert client.fetcher.warnings


def test_partial_failure_names_failed_outlet_without_losing_healthy_evidence(tmp_path):
    def opener(request, **kwargs):
        if 'dw.com' in request.full_url: raise OSError('synthetic offline')
        return io.BytesIO(feed().encode())
    cna = CNAClient(tmp_path, opener=opener, sleep=lambda _: None, today=DAY)
    client = ResearchClient(cna, ResearchConfig(), '2026.10.03')
    good = client._run('BBC', client.international[0].latest)
    bad = client._run('DW 中文', client.international[2].latest)
    assert good and not bad
    notice = client.notices(available=bool(good))[0]
    assert 'DW 中文' in notice and '部分查證來源' in notice
    assert 'BBC' not in notice


def test_government_items_in_facts_prompt_and_verbatim_alert_validation(tmp_path):
    from econ_digest.analysis.grounding import facts_unit, validate_fact_alerts
    from econ_digest.config import Config
    def opener(request, **kwargs):
        return io.BytesIO('<tr><td>115-10-01</td><td><a href="News_Content.aspx?n=95&amp;s=1">合成已完成變動公告</a></td></tr>'.encode())
    cna = CNAClient(tmp_path, opener=opener, sleep=lambda _: None)
    settings = replace(ResearchConfig(), cna=False)
    client = ResearchClient(cna, settings, '2026.10.03')
    # Isolate one enabled government source in this synthetic fixture.
    client.government = [GovernmentAdapter(GOVERNMENT[0], client.fetcher, DAY)]
    evidence = client.facts(['合成'])
    unit = facts_unit('2026.10.03', evidence, Config())
    assert '外交部' in unit.prompt and '合成已完成變動公告' in unit.prompt
    assert '政府第一手公告' in unit.prompt and unit.prompt_bytes <= 90_000
    source = evidence[0].source
    alert = {'fact': '合成舊值', 'suspected_new_value': '合成新值', 'evidence_url': source.url, 'evidence_title': source.title}
    data = {'alerts': [alert, {**alert, 'evidence_title': '改寫標題'}]}
    validate_fact_alerts(data, {source.url: source.title})
    assert data['alerts'] == [alert]


def test_source_lines_allow_named_approved_outlets_and_cap_three():
    from econ_digest.render.common import source_labels
    sources = [Source('公視', '2026-09-30', '合成新聞', 'https://news.pts.org.tw/article/123'),
               Source('BBC', '2026-10-01', 'Synthetic report', 'https://www.bbc.com/news/articles/synthetic'),
               Source('外交部', '2026-10-02', '合成公告', 'https://www.mofa.gov.tw/News_Content.aspx?n=95&s=1'),
               Source('聯合', '2026-10-02', '合成新聞二', 'https://udn.com/news/story/1/123')]
    labels = source_labels(sources)
    assert len(labels) == 3
    assert labels[0][0] == '公視 2026/09/30〈合成新聞〉'
    assert labels[1][0] == 'BBC 2026/10/01〈Synthetic report〉'
    assert source_labels([replace(sources[0], url='https://reuters.com/article/synthetic')]) == []


@pytest.mark.parametrize('url,expected', [
    ('https://www.cna.com.tw/search/hysearchws.aspx?q=synthetic', False),
    ('https://www.cna.com.tw/news/aipl/202610010001.aspx', True),
    ('https://www.cna.com.tw/search/allowed', True),
])
def test_robots_wildcards_longest_rule_and_exact_agent_groups(url, expected):
    from econ_digest.research.http import robots_allow
    rules = ['User-agent: *', 'Disallow: /', 'User-agent: econ-digest',
             'Content-signal: search=yes', 'Disallow: /search/*',
             'Allow: /news/', 'Allow: /search/allowed$']
    assert robots_allow(rules, url) is expected


@pytest.mark.parametrize('kind,ttl', [('robots', 86400), ('search', 7*86400), ('article', 30*86400), ('government', 6*3600)])
def test_each_cache_kind_expires_on_its_boundary(tmp_path, kind, ttl):
    calls, wall = [], [100.0]
    def opener(request, **kwargs): calls.append(request.full_url); return io.BytesIO(b'["synthetic"]')
    def get():
        return Fetcher(tmp_path, opener=opener, sleep=lambda _: None, wall_clock=lambda: wall[0]).cached('https://udn.com/synthetic', kind, json.loads)
    assert get() == ['synthetic']
    wall[0] += ttl-1
    assert get() == ['synthetic'] and len(calls) == 1
    wall[0] += 1
    assert get() == ['synthetic'] and len(calls) == 2


def test_redirects_also_consume_budget_and_apply_host_spacing(tmp_path):
    clock, calls, sleeps = [0.0], [], []
    def sleep(seconds): sleeps.append(seconds); clock[0] += seconds
    def opener(request, **kwargs):
        calls.append(request.full_url)
        if len(calls) == 1:
            headers = Message(); headers['Location'] = '/target'
            raise HTTPError(request.full_url, 302, '', headers, None)
        return io.BytesIO(b'ok')
    f = Fetcher(tmp_path, request_budget=2, opener=opener, clock=lambda: clock[0], sleep=sleep)
    assert f.fetch('https://udn.com/start') == 'ok'
    assert calls == ['https://udn.com/start', 'https://udn.com/target']
    assert sleeps == [2.5] and f.request_count == 2


def test_malformed_source_url_is_rejected():
    from econ_digest.research.parsers import source_url
    assert source_url('https://udn.com:bad/news/story/1/2', '聯合') is None
    assert source_url('https://[broken', '聯合') is None


def test_evidence_cap_keeps_twelve_distinct_entries_with_outlet_diversity():
    groups = [[Evidence('repeat', Source(outlet, '2026-10-01', f'{prefix}{i}', f'https://udn.com/news/story/1/{number+i}'), '合成摘錄') for i in range(10)]
              for outlet, prefix, number in [('中央社', '甲', 100), ('公視', '乙', 200), ('聯合', '丙', 300), ('自由', '丁', 400)]]
    result = merge_evidence(groups)
    assert len(result) == 12
    assert {e.source.outlet for e in result} == {'中央社', '公視', '聯合', '自由'}
    assert len({e.id for e in result}) == 12


def test_unparseable_domestic_search_falls_back_to_dated_feed(tmp_path):
    site = DOMESTIC[1]; calls = []
    def opener(request, **kwargs):
        calls.append(request.full_url)
        if request.full_url.endswith('robots.txt'): return io.BytesIO(b'User-agent: *\nAllow: /\n')
        if '/search/' in request.full_url: return io.BytesIO(b'<div id="js-only"></div>')
        return io.BytesIO(feed('https://udn.com/news/story/1/123', 'Synthetic Taiwan crisis').encode())
    adapter = DomesticAdapter(site, Fetcher(tmp_path, opener=opener, sleep=lambda _: None), DAY)
    result = adapter.retrieve(['台灣'])
    assert result[0].source.outlet == '聯合' and result[0].source.date == '2026-10-02'
    assert calls[-1] == site.rss


@pytest.mark.parametrize('body', [b'<rss><broken>', b'<html><body>synthetic challenge</body></html>'])
def test_bad_feed_is_an_isolated_source_failure(tmp_path, body):
    f = Fetcher(tmp_path, opener=lambda *args, **kwargs: io.BytesIO(body))
    assert RSSAdapter(INTERNATIONAL[0], f, DAY).latest() == []
    assert f.errors and not list(tmp_path.glob('*.json'))


def test_unparseable_government_list_is_reported_without_crashing(tmp_path):
    f = Fetcher(tmp_path, opener=lambda *args, **kwargs: io.BytesIO(b'<div>synthetic challenge</div>'))
    assert GovernmentAdapter(GOVERNMENT[0], f, DAY).latest() == []
    assert f.errors and not list(tmp_path.glob('*.json'))
