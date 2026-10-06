from dataclasses import replace
import json

import pytest

from econ_digest.config import ThreadsConfig
from econ_digest.models import ArticleSummary, Digest, load_json, save_json
from econ_digest.render.common import Entry
from econ_digest.social.formatting import FormatError, article_post, character_count
from econ_digest.social.queue import Queue, prepare_posts
from econ_digest.state import StateError


def test_queue_order_cover_and_merged_leader(issue_directory):
    posts = prepare_posts(issue_directory, ThreadsConfig())
    assert [p.article_id for p in posts] == ['intro', 'taiwan', 'focus', 'international', 'topics']
    assert posts[0].text.startswith('經濟學人導讀｜2026 年 10 月 3 日號\n合成封面故事｜共 5 篇文章')
    assert posts[0].image_url == 'https://example.invalid/covers/synthetic.jpg'
    assert all(p.image_url is None for p in posts[1:])
    assert posts[1].text.startswith('【台灣】合成taiwan標題\n\n')
    assert '（推論）與台灣的合成關聯。' in posts[1].text
    assert posts[2].link_url == 'https://telegra.ph/focus'
    assert all(character_count(p.text) <= 500 for p in posts)


def test_selection_retains_canonical_order(issue_directory):
    config = ThreadsConfig(sections=('財經・科技・文化', '台灣'), link_target='weekly', hashtags=('#導讀', '#台灣'))
    posts = prepare_posts(issue_directory, config)
    assert [p.article_id for p in posts] == ['intro', 'taiwan', 'topics']
    assert all(p.link_url == 'https://telegra.ph/weekly' for p in posts)
    assert all(p.text.endswith('#導讀 #台灣') for p in posts)


def test_idempotent_enqueue_preserves_container_and_post_ids(issue_directory, social_config):
    posts = prepare_posts(issue_directory, ThreadsConfig())
    q = Queue(social_config.paths.data_dir)
    assert q.enqueue(posts) == 5
    state = q.load()
    state['posts'][0].update(status='posted', post_id='posted-id', container_id='container-id', published_at='2026-10-06T00:00:00+00:00')
    q.save(state)
    assert q.enqueue([replace(p, text=p.text + '\n改版') for p in posts]) == 0
    assert q.load()['posts'][0] == state['posts'][0]
    assert Queue.next(q.load())['post']['article_id'] == 'taiwan'


def test_missing_cover_or_page_is_preview_only(issue_directory):
    (issue_directory / 'site_publish.json').unlink()
    (issue_directory / 'telegraph_pages.json').unlink()
    posts = prepare_posts(issue_directory, ThreadsConfig(), preview=True)
    assert len(posts) == 5
    with pytest.raises(ValueError):
        prepare_posts(issue_directory, ThreadsConfig())


def test_long_prose_drops_points_then_whole_sentences(issue_directory):
    digest = load_json(issue_directory / 'digest.json', Digest)
    entry = Entry(digest.issue.articles[0], digest.classifications['taiwan'], digest.summaries['taiwan'])
    entry.summary.headline_zh = '這是完整的一句話。' * 60
    entry.summary.key_points = ['可刪除的重點。' * 30, '另一個可刪除的重點。' * 30]
    entry.classification.taiwan_link = '（推論）台灣的關聯。https://example.invalid/taiwan'
    post = article_post(digest, entry, '台灣', 'https://telegra.ph/taiwan', ThreadsConfig())
    assert character_count(post.text) <= 500
    assert '・' not in post.text
    assert post.text.split('\n\n')[1].split('\n')[0].endswith('。')
    assert '（推論）台灣的關聯。https://example.invalid/taiwan' in post.text
    assert post.text.startswith('【台灣】' + entry.classification.title_zh)


def test_protected_keypoint_and_inference_survive(issue_directory):
    digest = load_json(issue_directory / 'digest.json', Digest)
    entry = Entry(digest.issue.articles[0], digest.classifications['taiwan'], digest.summaries['taiwan'])
    entry.summary.key_points = ['（推論）可能影響台灣。', '來源 https://example.invalid/taiwan', '可刪除的重點。' * 80]
    post = article_post(digest, entry, '台灣', 'https://telegra.ph/taiwan', ThreadsConfig())
    assert '・（推論）可能影響台灣。' in post.text
    assert 'https://example.invalid/taiwan' in post.text
    assert character_count(post.text) <= 500


def test_oversize_indivisible_sentence_fails_without_truncation(issue_directory):
    digest = load_json(issue_directory / 'digest.json', Digest)
    entry = Entry(digest.issue.articles[0], digest.classifications['taiwan'], digest.summaries['taiwan'])
    entry.summary.headline_zh = '長' * 600 + '。'
    with pytest.raises(FormatError):
        article_post(digest, entry, '台灣', 'https://telegra.ph/taiwan', ThreadsConfig())


@pytest.mark.parametrize(('text', 'count'), [('中文。ABC\n', 7), ('😀', 4), ('👍🏽', 8), ('👩\u200d💻', 11), ('❤️', 6)])
def test_meta_character_budget(text, count):
    assert character_count(text) == count


def test_corrupt_queue_never_discards_history(social_config, queued):
    queued.path.write_text('{bad json')
    with pytest.raises(StateError):
        queued.load()
    with pytest.raises(StateError):
        queued.enqueue([])
    assert queued.path.read_text() == '{bad json'
