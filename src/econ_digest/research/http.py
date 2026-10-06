"""Shared, bounded HTTP transport and parsed-data cache for approved evidence."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import ssl
import time
from collections import Counter
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import re

from ..models import save_json
from .cna import MAX_RESPONSE_BYTES, REQUEST_INTERVAL, USER_AGENT

logger = logging.getLogger(__name__)
TLS_HOSTS = frozenset({'www.mofa.gov.tw', 'www.president.gov.tw', 'www.stat.gov.tw'})
TTLS = {'robots': 86400, 'search': 7 * 86400, 'article': 30 * 86400,
        'rss': 6 * 3600, 'government': 6 * 3600}


def government_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=files(__package__).joinpath('certs/twca-secure-ssl.pem').read_text())
    return context


def robots_allow(lines: list[str], url: str) -> bool:
    """RFC-style group selection, wildcards and longest rule, also on Python 3.11.

    urllib.robotparser did not support * / $ matching on older Python versions.
    Unknown directives (including content signals) do not end an agent group.
    """
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    for line in [*lines, 'User-agent: __end__']:
        key, separator, value = line.split('#', 1)[0].partition(':')
        if not separator:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == 'user-agent':
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif key in {'allow', 'disallow'} and agents:
            rules.append((key == 'allow', value))
    product = USER_AGENT.split('/', 1)[0].lower()
    chosen: list[tuple[bool, str]] = []
    specificity = -1
    for agents, rules in groups:
        matches = [0 if agent == '*' else len(agent) for agent in agents
                   if agent == '*' or agent in product]
        if not matches:
            continue
        longest = max(matches)
        if longest > specificity:
            specificity, chosen = longest, list(rules)
        elif longest == specificity:
            chosen.extend(rules)
    parsed = urlsplit(url)
    path = unquote(parsed.path + ('?' + parsed.query if parsed.query else ''))
    matches = []
    for allow, rule in chosen:
        if not rule:
            continue
        rule = unquote(rule)
        end = rule.endswith('$')
        if end:
            rule = rule[:-1]
        pattern = '^' + '.*'.join(re.escape(part) for part in rule.split('*')) + ('$' if end else '')
        if re.search(pattern, path):
            matches.append((len(rule.replace('*', '')), allow))
    return max(matches, default=(0, True))[1]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Redirect requests must consume budget and respect host spacing too.


class Fetcher:
    def __init__(self, cache_dir: Path, *, request_budget: int = 120, timeout: float = 15,
                 max_retries: int = 3, opener: Callable[..., Any] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if type(request_budget) is not int or request_budget < 0:
            raise ValueError('request_budget must be nonnegative')
        if type(max_retries) is not int or not 0 <= max_retries <= 3:
            raise ValueError('max_retries must be 0–3')
        self.cache_dir = Path(cache_dir)
        self.request_budget, self.timeout, self.max_retries = request_budget, timeout, max_retries
        self.clock, self.wall_clock, self.sleep = clock, wall_clock, sleep
        self._open = opener or build_opener(_NoRedirect()).open
        self._government_open = opener or build_opener(_NoRedirect(), HTTPSHandler(context=government_ssl_context())).open
        self._last: dict[str, float] = {}
        self.request_count = 0
        self.requests: Counter[str] = Counter()
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[str] = []
        self.robots_decisions: dict[str, bool] = {}
        self._once: dict[tuple[str, str], Any] = {}
        self._robots: dict[str, list[str] | None] = {}

    def _retry_after(self, exc: HTTPError) -> float:
        value = exc.headers.get('Retry-After', '') if exc.headers else ''
        try:
            delay = float(value)
        except ValueError:
            try:
                delay = parsedate_to_datetime(value).timestamp() - self.wall_clock()
            except (ValueError, TypeError, OverflowError):
                return 0
        return max(0, delay) if math.isfinite(delay) else 0

    def fetch(self, url: str) -> str | None:
        delay = 0.0
        retries = redirects = 0
        while True:
            host = urlsplit(url).hostname or ''
            if urlsplit(url).scheme != 'https' or not host or urlsplit(url).username:
                self.errors.append((url, 'unsafe_url'))
                return None
            if self.request_count >= self.request_budget:
                if not self.warnings:
                    notice = f'查證每次分析請求上限（{self.request_budget} 次）已達；後續查證僅使用快取。'
                    self.warnings.append(notice)
                    logger.warning('%s', notice)
                self.errors.append((url, 'request_budget'))
                return None
            spacing = max(0, REQUEST_INTERVAL - (self.clock() - self._last[host])) if host in self._last else 0
            if max(delay, spacing):
                self.sleep(max(delay, spacing))
            self._last[host] = self.clock()
            self.request_count += 1
            self.requests[host] += 1
            try:
                request = Request(url, headers={'User-Agent': USER_AGENT})
                opener = self._government_open if host in TLS_HOSTS else self._open
                with opener(request, timeout=self.timeout) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise ValueError('response too large')
                return raw.decode('utf-8-sig', errors='replace')
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308} and redirects < 5:
                    newurl = urljoin(url, exc.headers.get('Location', ''))
                    exc.close()
                    if newurl == url:
                        self.errors.append((url, 'redirect_loop'))
                        return None
                    url, delay, redirects = newurl, 0, redirects + 1
                    continue
                if exc.code in {429, 503} and retries < self.max_retries:
                    delay = max(REQUEST_INTERVAL * 2 ** retries, self._retry_after(exc))
                    retries += 1
                    exc.close()
                    continue
                self.errors.append((url, f'HTTPError:{exc.code}'))
                exc.close()
                return None
            except (OSError, ValueError, TimeoutError) as exc:
                self.errors.append((url, type(exc).__name__))
                return None

    def cached(self, url: str, kind: str, parse: Callable[[str], Any], *, once: bool = False) -> Any:
        key = (kind, url)
        if once and key in self._once:
            return self._once[key]
        path = self.cache_dir / (hashlib.sha256((kind + ':' + url).encode()).hexdigest() + '.json')
        data = None
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            if saved['url'] == url and saved['kind'] == kind and 0 <= self.wall_clock() - saved['time'] < TTLS[kind]:
                data = saved['data']
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if data is None:
            text = self.fetch(url)
            if text is not None:
                try:
                    data = parse(text)
                    save_json(path, {'url': url, 'kind': kind, 'time': self.wall_clock(), 'data': data})
                except (ValueError, TypeError, KeyError, SyntaxError) as exc:
                    self.errors.append((url, type(exc).__name__))
        data = [] if data is None else data
        if once:
            self._once[key] = data
        paths = sorted(self.cache_dir.glob('*.json'), key=lambda item: item.stat().st_mtime)
        for stale in paths[:-1000]:
            stale.unlink(missing_ok=True)
        return data

    def search_allowed(self, url: str) -> bool:
        host = urlsplit(url).netloc
        if host not in self._robots:
            robots = 'https://' + host + '/robots.txt'
            before = len(self.errors)
            lines = self.cached(robots, 'robots', lambda body: body.splitlines(), once=True)
            failures = self.errors[before:]
            if failures and failures[-1][1] == 'HTTPError:404':
                lines = []  # No robots file means no restriction.
                self.errors.pop()
                path = self.cache_dir / (hashlib.sha256(('robots:' + robots).encode()).hexdigest() + '.json')
                save_json(path, {'url': robots, 'kind': 'robots', 'time': self.wall_clock(), 'data': []})
            self._robots[host] = None if failures and failures[-1][1] != 'HTTPError:404' else lines
        lines = self._robots[host]
        allowed = lines is not None and robots_allow(lines, url)
        self.robots_decisions[url] = allowed
        if not allowed:
            logger.info('robots 未允許搜尋 %s，改用該站 RSS。', url)
        return allowed
