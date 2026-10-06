"""One analysis-scoped evidence client sharing every request and source setting."""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta
from difflib import SequenceMatcher
from itertools import zip_longest
from urllib.request import urlopen

from ..config import ResearchConfig
from ..models import Article
from ..signals import find_taiwan_signals
from .cna import CNAClient, Evidence, url_date
from .domestic import DomesticAdapter
from .government import GovernmentAdapter
from .http import Fetcher
from .rss import RSSAdapter, keywords, match
from .sources import CNA_RSS, DOMESTIC, GOVERNMENT, INTERNATIONAL, Site

logger = logging.getLogger(__name__)


def merge_evidence(groups: list[list[Evidence]], limit: int = 12) -> list[Evidence]:
    """Round-robin sources to keep outlet diversity, deduplicating close headlines."""
    kept, titles, urls = [], [], set()
    for row in zip_longest(*groups):
        for entry in row:
            if entry is None: continue
            title = re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', entry.source.title)).casefold()
            if entry.source.url in urls or any(title == old or (min(len(title), len(old)) >= 12
                       and SequenceMatcher(None, title, old).ratio() >= .9) for old in titles):
                continue
            titles.append(title)
            urls.add(entry.source.url)
            kept.append(Evidence(f'ev{len(kept) + 1}', entry.source, entry.excerpt[:200]))
            if len(kept) >= limit: return kept
    return kept


class ResearchClient:
    def __init__(self, cna: CNAClient, settings: ResearchConfig, issue_date: str):
        self.cna, self.settings = cna, settings
        self.issue_date = date.fromisoformat(issue_date.replace('.', '-'))
        # Retain injected transport/clock support and CNA's existing cache format.
        self.fetcher = Fetcher(cna.cache_dir, request_budget=settings.request_budget,
                               opener=cna.opener if cna.opener is not urlopen else None,
                               sleep=cna.sleep, clock=cna.clock, wall_clock=cna.wall_clock,
                               timeout=cna.timeout, max_retries=cna.max_retries)
        cna.fetcher = self.fetcher
        self.domestic = [DomesticAdapter(site, self.fetcher, self.issue_date) for site in DOMESTIC if getattr(settings, site.key)]
        self.international = [RSSAdapter(site, self.fetcher, self.issue_date) for site in INTERNATIONAL if getattr(settings, site.key)]
        self.government = [GovernmentAdapter(site, self.fetcher, self.issue_date) for site in GOVERNMENT if getattr(settings, site.key)]
        self.failed: set[str] = set()
        self.evidence_by_article: dict[str, list[Evidence]] = {}

    def _run(self, outlet, operation):
        before = len(self.fetcher.errors)
        before_cna = len(self.cna.errors)
        result = operation()
        if len(self.fetcher.errors) > before or (outlet == '中央社' and len(self.cna.errors) > before_cna):
            self.failed.add(outlet)
        self.cna.request_count = self.fetcher.request_count
        for notice in self.fetcher.warnings:
            if notice not in self.cna.warnings: self.cna.warnings.append(notice)
        return result

    def _cna(self, queries: list[str], *, headlines: bool = False) -> list[Evidence]:
        if not self.settings.cna: return []
        # CNA.search checks robots when attached to this shared transport.
        entries = self.cna.retrieve_search(queries) if headlines else self.cna.retrieve(queries)
        entries = [e for e in entries if (published := url_date(e.source.url))
                   and self.issue_date - timedelta(days=365) <= published <= self.issue_date]
        if getattr(self.cna, 'robots_blocked', False):
            feed = RSSAdapter(Site('cna', '中央社', CNA_RSS), self.fetcher, self.issue_date)
            entries.extend(feed.retrieve(keywords(queries)))
        return entries

    def retrieve(self, queries: list[str], article: Article) -> list[Evidence]:
        terms = keywords(queries, article.title, article.rubric or '', find_taiwan_signals(article).snippets)
        groups = [self._run('中央社', lambda: self._cna(queries))]
        groups.extend(self._run(adapter.site.outlet, lambda a=adapter: a.retrieve(queries)) for adapter in self.domestic)
        international = []
        for adapter in self.international:
            international.extend(self._run(adapter.site.outlet, lambda a=adapter: a.retrieve(terms)))
        groups.append(match(international, terms, 3))
        official = []
        for adapter in self.government:
            official.extend(self._run(adapter.site.outlet, lambda a=adapter: a.retrieve(terms)))
        groups.insert(1, match(official, terms, 3))
        entries = merge_evidence(groups)
        self.evidence_by_article[article.id] = entries
        logger.info('查證證據 %s：%s', article.id,
                    ', '.join(f'{outlet} {sum(e.source.outlet == outlet for e in entries)}' for outlet in sorted({e.source.outlet for e in entries})))
        return entries

    def facts(self, queries: list[str]) -> list[Evidence]:
        groups = [self._run('中央社', lambda: self._cna(queries, headlines=True))]
        groups.extend(self._run(a.site.outlet, a.latest) for a in self.government)
        # All agency lists fit in the 90 KB prompt after a bounded, diverse merge.
        return merge_evidence(groups, 100)

    def notices(self, *, available: bool, facts: bool = False) -> list[str]:
        if not self.failed: return []
        names = '、'.join(sorted(self.failed))
        suffix = '台灣事實檔更新檢查僅能使用已取得的證據。' if facts else '台灣關聯改以原文、事實檔與已取得的證據查證。'
        if available:
            return [f'部分查證來源暫時無法連線或解析（{names}）；{suffix}']
        notices = [f'查證來源暫時無法連線或解析（{names}）；{suffix}']
        if '中央社' in self.failed:
            notices.insert(0, '中央社暫時無法連線；' + suffix)
        return notices


def for_analysis(cna: CNAClient, settings: ResearchConfig, issue_date: str) -> ResearchClient:
    client = getattr(cna, '_research', None)
    if client is None or client.settings != settings or client.issue_date.isoformat() != issue_date.replace('.', '-'):
        client = ResearchClient(cna, settings, issue_date)
        cna._research = client
    return client
