"""Government press lists, including source-owned Nuxt payloads at CEC."""
from __future__ import annotations

import json
from datetime import date

from ..models import Source
from .cna import Evidence
from .http import Fetcher
from .parsers import Page, clean, parse_date, parse_html_list, recent
from .rss import match, restore
from .sources import Site


def parse_cec(body: str, base: str) -> list[Evidence]:
    page = Page()
    page.feed(body)
    results = parse_html_list(body, '中選會', base)
    for node in page.root.walk():
        if node.attrs.get('id') != '__NUXT_DATA__': continue
        try:
            table = json.loads(node.text())
            if not isinstance(table, list): continue
            # Nuxt/devalue serialises dictionary values as references into a table.
            for obj in table:
                if not isinstance(obj, dict) or not {'articleId', 'title', 'beginTime'} <= obj.keys(): continue
                identifier, title, timestamp = [table[obj[key]] for key in ('articleId', 'title', 'beginTime')]
                published = parse_date(str(timestamp)[:8])
                if str(identifier).isdigit() and isinstance(title, str) and published:
                    url = f'https://www.cec.gov.tw/central/article/{identifier}'
                    results.append(Evidence('', Source('中選會', published.isoformat(), clean(title), url), clean(title)))
        except (ValueError, TypeError, IndexError, KeyError):
            continue
    return list({e.source.url: e for e in results}.values())


class GovernmentAdapter:
    def __init__(self, site: Site, fetcher: Fetcher, issue_date: date):
        self.site, self.fetcher, self.issue_date = site, fetcher, issue_date

    def latest(self) -> list[Evidence]:
        parser = parse_cec if self.site.key == 'cec' else lambda body, url: parse_html_list(body, self.site.outlet, url)
        def parse(body):
            entries = parser(body, self.site.url)
            if not entries:
                raise ValueError('government list could not be parsed')
            return [e.to_dict() for e in entries]
        data = self.fetcher.cached(self.site.url, 'government', parse, once=True)
        # Official final statistics can be older than a two-week news cycle.
        return recent(restore(data), self.issue_date, 365)[:20]

    def retrieve(self, terms: set[str]) -> list[Evidence]:
        return match(self.latest(), terms)
