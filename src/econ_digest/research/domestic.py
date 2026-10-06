"""Domestic site searches with robots-aware RSS fallback."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

from ..models import Source
from .cna import Evidence
from .http import Fetcher, logger
from .parsers import Page, _article_path, clean, parse_article, parse_html_list, recent, source_url
from .rss import RSSAdapter, keywords, restore
from .sources import Site


def parse_candidates(body: str, site: Site, base: str) -> list[dict[str, str]]:
    """Undated own-site hits are candidates only; article metadata supplies the date."""
    page = Page()
    page.feed(body)
    found = {}
    for node in page.root.walk():
        if node.tag != 'a': continue
        url = source_url(node.attrs.get('href'), site.outlet, base)
        title = clean(node.attrs.get('title') or node.text())
        if url and _article_path(url, site.outlet) and len(title) >= 4:
            found.setdefault(url, {'url': url, 'title': title})
    return list(found.values())


class DomesticAdapter:
    def __init__(self, site: Site, fetcher: Fetcher, issue_date: date):
        self.site, self.fetcher, self.issue_date = site, fetcher, issue_date

    def _rss(self, queries: list[str]) -> list[Evidence]:
        logger.info('%s 搜尋無可解析結果或 robots 未允許，改用 RSS。', self.site.outlet)
        feed = Site(self.site.key, self.site.outlet, self.site.rss)
        return RSSAdapter(feed, self.fetcher, self.issue_date).retrieve(keywords(queries))

    def retrieve(self, queries: list[str]) -> list[Evidence]:
        found = {}
        for query in queries:
            url = self.site.url.format(query=quote(query, safe=''))
            if not self.fetcher.search_allowed(url):
                for entry in self._rss(queries): found.setdefault(entry.source.url, entry)
                break
            def parse(body):
                return {'dated': [e.to_dict() for e in parse_html_list(body, self.site.outlet, url)],
                        'candidates': parse_candidates(body, self.site, url)}
            data = self.fetcher.cached(url, 'search', parse)
            dated = restore(data.get('dated', [])) if isinstance(data, dict) else []
            hits = recent(dated, self.issue_date, 365)
            known = {e.source.url for e in dated}
            candidates = [item for item in data.get('candidates', []) if item['url'] not in known] if isinstance(data, dict) else []
            # New LTN hits expose relative list times. Never manufacture dates from them.
            for item in candidates[:3]:
                article = self.fetcher.cached(item['url'], 'article', lambda body: [v.isoformat() if isinstance(v, date) else v for v in parse_article(body)])
                if isinstance(article, list) and len(article) == 3 and article[2]:
                    source = Source(self.site.outlet, article[2], article[0] or item['title'], item['url'])
                    hits.extend(recent([Evidence('', source, article[1] or source.title[:200])], self.issue_date, 365))
            for entry in hits[:5]: found.setdefault(entry.source.url, entry)
            if not dated and not candidates:
                for entry in self._rss(queries): found.setdefault(entry.source.url, entry)
        return list(found.values())[:8]
