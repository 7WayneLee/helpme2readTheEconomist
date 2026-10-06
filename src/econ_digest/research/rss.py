"""Once-per-run recent feed retrieval and deterministic keyword matching."""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import date

from ..models import Source
from ..zhtw.normalize import _convert_batch
from .cna import Evidence
from .http import Fetcher
from .parsers import parse_rss, recent
from .sources import Site

STOP_WORDS = {'about', 'after', 'again', 'against', 'answer', 'before', 'between', 'could',
              'from', 'have', 'into', 'more', 'that', 'their', 'there', 'these', 'this',
              'uses', 'what', 'when', 'where', 'which', 'with', 'would', 'will', 'your'}
GENERIC = {'taiwan', 'taiwanese', 'china', 'chinese', '台灣', '臺灣', '中國'}


def keywords(queries: list[str], title: str = '', rubric: str = '', signals: list[str] = ()) -> set[str]:
    words = {word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", ' '.join([title, rubric, *signals]))
             if word.casefold() not in STOP_WORDS}
    for query in queries:
        words.update(part.casefold() for part in re.findall(r'[\u3400-\u9fff]{2,}|[A-Za-z][A-Za-z-]{2,}', query))
    if '台灣' in words or '臺灣' in words:
        words.update({'台灣', '臺灣', 'taiwan', 'taiwanese'})
    if '中國' in words:
        words.update({'中國', 'china', 'chinese'})
    return words


def score(entry: Evidence, terms: set[str]) -> int:
    text = (entry.source.title + ' ' + entry.excerpt).casefold()
    return sum((1 if term in GENERIC else 3) for term in terms
               if (bool(re.search(r'(?<![a-z])' + re.escape(term) + r'(?![a-z])', text))
                   if term.isascii() else term in text))


def match(entries: list[Evidence], terms: set[str], limit: int = 3) -> list[Evidence]:
    ranked = [(score(entry, terms), entry) for entry in entries]
    ranked.sort(key=lambda pair: (pair[0], pair[1].source.date), reverse=True)
    return [entry for points, entry in ranked if points > 0][:limit]


def restore(data: object) -> list[Evidence]:
    result = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and all(isinstance(item.get(k), str) for k in ('outlet', 'date', 'title', 'url', 'excerpt')):
            result.append(Evidence('', Source(item['outlet'], item['date'], item['title'], item['url']), item['excerpt'][:200]))
    return result


class RSSAdapter:
    def __init__(self, site: Site, fetcher: Fetcher, issue_date: date):
        self.site, self.fetcher, self.issue_date = site, fetcher, issue_date

    def latest(self) -> list[Evidence]:
        data = self.fetcher.cached(self.site.url, 'rss',
                                   lambda body: [e.to_dict() for e in parse_rss(body, self.site.outlet, self.site.url)], once=True)
        entries = recent(restore(data), self.issue_date, 14)
        if self.site.key == 'dw':
            # Convert fresh and already cached feeds before matching/evidence.
            # Reuse script conversion only: quoted titles retain their wording,
            # punctuation and links, without the model-text glossary rewrites.
            converted = iter(_convert_batch([text for entry in entries
                                            for text in (entry.source.title, entry.excerpt)]))
            entries = [replace(entry, source=replace(entry.source, title=next(converted)),
                               excerpt=next(converted)[:200]) for entry in entries]
        return entries

    def retrieve(self, terms: set[str]) -> list[Evidence]:
        return match(self.latest(), terms)
