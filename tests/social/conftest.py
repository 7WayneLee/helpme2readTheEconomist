from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from econ_digest.config import Config, PathsConfig, SecretsConfig, SocialConfig, ThreadsConfig
from econ_digest.models import ArticleSummary, Classification, Digest
from econ_digest.models import save_json
from econ_digest.social.formatting import Post
from econ_digest.social.queue import Queue


@pytest.fixture
def now():
    return datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)  # 08:00 台北


@pytest.fixture
def social_config(tmp_path, now):
    return Config(paths=PathsConfig(tmp_path / 'data', tmp_path / 'output'),
                  social=SocialConfig(ThreadsConfig(enabled=True)),
                  secrets=SecretsConfig(threads_access_token='synthetic-private-token', threads_user_id='synthetic-user',
                                        threads_token_issued_at=now.isoformat(), telegram_bot_token='synthetic-tg',
                                        telegram_chat_id='12345'))


@pytest.fixture
def post():
    return Post('2026.10.03:story', '2026.10.03', 'story', '國際',
                '合成標題\n\n合成一句話。\n\nhttps://telegra.ph/synthetic',
                'https://telegra.ph/synthetic', topic_tag='經濟學人導讀')


@pytest.fixture
def queued(social_config, post):
    q = Queue(social_config.paths.data_dir)
    q.enqueue([post, replace(post, key='2026.10.03:second', article_id='second')])
    return q


@pytest.fixture
def issue_directory(synthetic_issue, social_config):
    base = synthetic_issue.articles[0]
    specifications = [('taiwan', 2, 'tech', 'B'), ('focus', 0, 'finance', 'A'),
                      ('international', 0, 'intl.china', 'C'), ('topics', 0, 'culture', 'D')]
    articles, classes, summaries = [], {}, {}
    for order, (identifier, level, category, tier) in enumerate(specifications):
        article = replace(base, id=identifier, order=order, kind='article', is_cover=False)
        articles.append(article)
        classes[identifier] = Classification(identifier, level, bool(level), '（推論）與台灣的合成關聯。' if level else None,
                                              category, '合成' + identifier + '標題', tier=tier)
        summaries[identifier] = ArticleSummary(identifier, tier, '合成一句話重點。', key_points=['合成重點一。', '合成重點二。'])
    leader = replace(base, id='leader', order=8, kind='leader', is_cover=True)
    articles.append(leader)
    classes['leader'] = Classification('leader', 0, False, None, 'finance', '合成封面故事', 'focus', 'merged')
    # Include an erroneous lingering merged summary; never give it a post.
    summaries['leader'] = ArticleSummary('leader', 'B', '合成合併內容。')
    digest = Digest(synthetic_issue.issue_date, '2026-10-05T00:00:00+00:00', replace(synthetic_issue, articles=articles),
                    classes, summaries, None, None, focus_ids=['focus'])
    path = social_config.paths.data_dir / 'issues' / 'te_2026.10.03'
    path.mkdir(parents=True)
    save_json(path / 'digest.json', digest)
    save_json(path / 'site_publish.json', {'cover_url': 'https://example.invalid/covers/synthetic.jpg'})
    save_json(path / 'telegraph_pages.json', [dict(key=group + ':1', path=group, url='https://telegra.ph/' + group)
                                            for group in ('weekly', 'taiwan', 'focus', 'international', 'topics')])
    return path


class Response:
    def __init__(self, data, status=200, headers=None):
        self.data, self.status, self.headers = data, status, headers or {}
    def read(self):
        return json.dumps(self.data).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
    def open(self, request, **kwargs):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
