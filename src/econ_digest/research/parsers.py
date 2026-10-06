"""Small HTML/RSS parsers: source-owned dates, approved URLs and short excerpts."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

from ..models import Source
from .cna import Evidence, _objects

# Public sources only. Host validation also protects source-line rendering.
OUTLET_HOSTS = {
    '中央社': {'www.cna.com.tw'}, '公視': {'news.pts.org.tw'},
    '聯合': {'udn.com'}, '自由': {'news.ltn.com.tw', 'ec.ltn.com.tw', 'def.ltn.com.tw', 'ent.ltn.com.tw', 'sports.ltn.com.tw', 'istyle.ltn.com.tw', '3c.ltn.com.tw', 'auto.ltn.com.tw'},
    'BBC': {'www.bbc.com', 'www.bbc.co.uk'}, 'BBC 中文': {'www.bbc.com', 'www.bbc.co.uk'},
    'DW 中文': {'www.dw.com', 'dw.com'}, 'RFI 中文': {'www.rfi.fr'},
    'The Guardian': {'www.theguardian.com'},
    '外交部': {'www.mofa.gov.tw'}, '國防部': {'www.mnd.gov.tw'},
    '總統府': {'www.president.gov.tw'}, '行政院': {'www.ey.gov.tw'},
    '主計總處': {'www.stat.gov.tw', 'www.dgbas.gov.tw'},
    '中選會': {'www.cec.gov.tw', 'web.cec.gov.tw'},
}


def source_url(value: Any, outlet: str | None = None, base: str = '') -> str | None:
    if not isinstance(value, str):
        return None
    try:
        url = urljoin(base, value.strip())
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    allowed = OUTLET_HOSTS.get(outlet, set()) if outlet else set().union(*OUTLET_HOSTS.values())
    if parsed.scheme not in {'https', 'http'} or parsed.hostname not in allowed or parsed.username or port not in {None, 80, 443}:
        return None
    return urlunsplit(('https', parsed.hostname, parsed.path, parsed.query, ''))


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    # ISO/slash dates, ROC calendar dates and Chinese written dates.
    match = re.search(r'(?<!\d)(\d{3,4})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?', value)
    compact = re.search(r'(?<!\d)((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)', value)
    try:
        if match or compact:
            y, m, d = map(int, (match or compact).groups())
            return date(y + 1911 if y < 1911 else y, m, d)
        return parsedate_to_datetime(value).date()
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass
class Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)
    parent: Node | None = None

    def text(self) -> str:
        return ''.join(child.text() if isinstance(child, Node) else child for child in self.children)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node('root')

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), parent=self.current)
        self.current.children.append(node)
        if tag not in {'meta', 'link', 'br', 'hr', 'input', 'img', 'source', 'wbr', 'area', 'embed'}:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, dict(attrs), parent=self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                break
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def clean(value: str) -> str:
    parser = Page()
    parser.feed(value)
    return ' '.join(parser.root.text().split())[:200]


def recent(entries: list[Evidence], today: date, days: int) -> list[Evidence]:
    return [entry for entry in entries if (published := parse_date(entry.source.date))
            and today - timedelta(days=days) <= published <= today]


def parse_rss(body: str, outlet: str, base: str) -> list[Evidence]:
    root = ET.fromstring(body)
    if root.tag.rsplit('}', 1)[-1] not in {'rss', 'RDF', 'feed'}:
        raise ValueError('unexpected RSS document')
    result = {}
    for item in root.iter():
        if item.tag.rsplit('}', 1)[-1] not in {'item', 'entry'}:
            continue
        values = {child.tag.rsplit('}', 1)[-1]: child for child in item}
        def value(key):
            node = values.get(key)
            return ''.join(node.itertext()).strip() if node is not None else ''
        link = values.get('link')
        url = source_url(value('link') or (link.get('href') if link is not None else ''), outlet, base)
        published = parse_date(value('pubDate') or value('published') or value('date') or value('updated'))
        title = clean(value('title'))
        if url and published and title:
            result.setdefault(url, Evidence('', Source(outlet, published.isoformat(), title, url),
                                            clean(value('description') or value('summary') or value('encoded'))))
    return list(result.values())


def _article_path(url: str, outlet: str) -> bool:
    path = urlsplit(url).path
    patterns = {'公視': r'/article/\d+', '聯合': r'/news/story/\d+/\d+',
                '自由': r'/news/(?:\w+/)?(?:breakingnews/)?\d+|/article/breakingnews/\d+',
                '外交部': r'/News_Content.aspx', '主計總處': r'/News_Content.aspx',
                '總統府': r'/NEWS/\d+', '行政院': r'/Page/[A-Z0-9]+/[a-z0-9-]+',
                '國防部': r'/news/(?:plaact|pressrelease)/\d+',
                '中選會': r'/.*article/\d+'}
    return bool(re.search(patterns.get(outlet, r'.'), path, re.I))


def parse_html_list(body: str, outlet: str, base: str) -> list[Evidence]:
    page = Page()
    page.feed(body)
    base_node = next((n for n in page.root.walk() if n.tag == 'base'), None)
    if base_node is not None:
        base = urljoin(base, base_node.attrs.get('href') or '')
    found = {}
    # Source-published JSON-LD or inline list JSON, never external search engines.
    for node in page.root.walk():
        if node.tag != 'script':
            continue
        try:
            payload = json.loads(node.text())
        except ValueError:
            continue
        for obj in _objects(payload):
            url = source_url(obj.get('url') or obj.get('@id') or obj.get('link'), outlet, base)
            published = parse_date(obj.get('datePublished') or obj.get('date') or obj.get('time'))
            title = obj.get('headline') or obj.get('name') or obj.get('title')
            if url and _article_path(url, outlet) and published and isinstance(title, str) and title.strip():
                found.setdefault(url, Evidence('', Source(outlet, published.isoformat(), clean(title), url),
                                                clean(obj.get('description') or title)))
    for node in page.root.walk():
        if node.tag != 'a':
            continue
        url = source_url(node.attrs.get('href'), outlet, base)
        heading = next((child for child in node.walk() if 'title' in (child.attrs.get('class') or '').split()), None)
        title = node.attrs.get('title') or (heading.text().strip() if heading else node.text().strip())
        if not url or not _article_path(url, outlet) or not title or len(title) < 4:
            continue
        published = parse_date(urlsplit(url).path)
        block = node
        for _ in range(5):
            # Prefer datetime attributes to visible list dates.
            dated = [child.attrs.get('datetime', '') for child in block.walk() if child.tag == 'time']
            published = published or next((d for v in dated if (d := parse_date(v))), None) or parse_date(block.text())
            if published or block.parent is None or len(block.parent.text()) > 3000:
                break
            block = block.parent
        if published:
            found.setdefault(url, Evidence('', Source(outlet, published.isoformat(), clean(title), url), clean(title)))
    return list(found.values())


def parse_article(body: str) -> tuple[str, str, date | None]:
    page = Page()
    page.feed(body)
    title, excerpt, published = '', '', None
    for node in page.root.walk():
        if node.tag == 'meta':
            key = node.attrs.get('property') or node.attrs.get('name')
            val = node.attrs.get('content') or ''
            if key == 'og:title': title = clean(val)
            if key in {'og:description', 'description'} and not excerpt: excerpt = clean(val)
            if key in {'article:published_time', 'date', 'datePublished'}: published = parse_date(val)
        if node.tag == 'h1' and not title: title = clean(node.text())
        if node.tag == 'script' and 'ld+json' in (node.attrs.get('type') or ''):
            try:
                for obj in _objects(json.loads(node.text())):
                    if obj.get('datePublished'):
                        published = parse_date(obj['datePublished']) or published
                        title = clean(obj.get('headline') or title)
                        excerpt = clean(obj.get('description') or excerpt)
            except ValueError:
                pass
    return title, excerpt, published
