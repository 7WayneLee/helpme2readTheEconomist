from __future__ import annotations

import json
from pathlib import Path

from econ_digest.models import Digest, Source
from econ_digest.render.common import source_labels
from econ_digest.render.html import render_html
from econ_digest.render.markdown import render_markdown
from econ_digest.render.telegraph import article_nodes, render_telegraph, summary_message
from econ_digest.render.telegram import render_telegram
from econ_digest.site import build_site


def add_sources(digest: Digest) -> list[Source]:
    sources = [Source('中央社', '2026-09-29', f'合成來源{i}',
                      f'https://www.cna.com.tw/news/aipl/20260929000{i}.aspx') for i in range(1, 5)]
    digest.classifications['sample-1'].sources = sources
    digest.summaries['sample-1'].sources = sources
    return sources


def test_sources_in_reports_site_telegraph_but_not_chat(sample_digest: Digest, tmp_path: Path) -> None:
    sources = add_sources(sample_digest)
    html = render_html(sample_digest)
    markdown = render_markdown(sample_digest)
    pages = render_telegraph(sample_digest)
    telegraph = json.dumps([page.nodes for page in pages], ensure_ascii=False)
    site = build_site(sample_digest, tmp_path)
    site_html = site.pages['taiwan'].read_text()
    for content in (html, markdown, telegraph, site_html):
        assert '依據：' in content and '中央社 2026/09/29〈合成來源1〉' in content
        assert sources[0].url in content and sources[2].url in content
        assert sources[3].url not in content
    assert '依據：' not in '\n'.join(render_telegram(sample_digest))
    assert 'cna.com.tw' not in summary_message(sample_digest, pages, {page.key: 'https://telegra.ph/synthetic' for page in pages})


def test_sources_safe_url_dedup_and_e_tier_placement(sample_digest: Digest) -> None:
    sources = add_sources(sample_digest)
    bad = Source('合成', '2026-10-01', '<script>', 'javascript:alert(1)')
    assert len(source_labels([sources[0], sources[0], bad])) == 1
    sample_digest.summaries['sample-1'].tier = 'E'
    from econ_digest.render.common import entries
    entry = next(item for item in entries(sample_digest) if item.article.id == 'sample-1')
    nodes = json.dumps(article_nodes(sample_digest, entry), ensure_ascii=False)
    assert '與台灣的關聯' in nodes and '對台灣的意涵' in nodes and '依據：' in nodes
