from __future__ import annotations

from collections.abc import Callable
import json
import re

import pytest

from econ_digest.models import Digest
from econ_digest.render import render_html, render_markdown, render_telegram
from econ_digest.render.telegraph import render_telegraph, summary_message, with_navigation


def telegram_text(digest: Digest) -> str:
    return "\n".join(render_telegram(digest))


def telegraph_text(digest: Digest) -> str:
    pages = render_telegraph(digest)
    urls = {page.key: f"https://telegra.ph/synthetic-{index}" for index, page in enumerate(pages)}
    return "\n".join(page.title + json.dumps(page.nodes, ensure_ascii=False)
                     for page in with_navigation(pages, urls))


def telegraph_summary(digest: Digest) -> str:
    pages = render_telegraph(digest)
    urls = {page.key: f"https://telegra.ph/synthetic-{index}" for index, page in enumerate(pages)}
    return summary_message(digest, pages, urls)


@pytest.mark.parametrize("render", [render_markdown, render_html, telegram_text, telegraph_text, telegraph_summary])
@pytest.mark.parametrize("no_taiwan", [False, True])
def test_all_renderers_use_neutral_taiwan_labels(sample_digest: Digest, no_taiwan_digest: Digest,
                                                render: Callable[[Digest], str], no_taiwan: bool) -> None:
    rendered = render(no_taiwan_digest if no_taiwan else sample_digest)
    assert not re.search("[\U0001f1e6-\U0001f1ff]", rendered)
    if render is telegraph_summary:
        assert "與台灣相關" not in rendered
        assert "• " not in rendered
        assert (">台灣</a>" in rendered) == (not no_taiwan)
    else:
        # Weekly brief relevance is independent of the presence of Taiwan articles.
        assert rendered.count("【台灣相關】") == 2
        assert rendered.index("台灣相關政治要聞") < rendered.index("非台灣政治要聞")
        assert rendered.index("台灣商業合成要聞") < rendered.index("商業合成要聞")
        if render is render_html:
            assert '<span class="badge taiwan">【台灣相關】</span>' in rendered
        if render is telegram_text:
            if no_taiwan:
                assert "台灣：本期沒有台灣相關文章。" not in rendered
            else:
                for level in (1, 2, 3):
                    assert f"<b>T{level} · " in rendered
                assert "<b>間接相關</b>" in rendered


@pytest.mark.parametrize("render", [render_markdown, render_html, telegram_text, telegraph_text, telegraph_summary])
def test_no_labels_when_no_taiwan_articles_or_brief_items(no_taiwan_digest: Digest,
                                                        render: Callable[[Digest], str]) -> None:
    assert no_taiwan_digest.week_brief is not None
    for item in [*no_taiwan_digest.week_brief.politics, *no_taiwan_digest.week_brief.business]:
        item.taiwan_related = False
    rendered = render(no_taiwan_digest)
    assert not re.search("[\U0001f1e6-\U0001f1ff]", rendered)
    assert "【台灣相關】" not in rendered
    assert "<b>與台灣相關</b>" not in rendered


def test_summary_omits_taiwan_headlines(sample_digest: Digest) -> None:
    sample_digest.classifications["sample-4"].taiwan_level = 1
    rendered = telegraph_summary(sample_digest)
    assert "與台灣相關" not in rendered and "• " not in rendered
    for headline in ("台灣晶片展望", "美國政策", "台灣與國際合作", "供應鏈間接影響"):
        assert headline not in rendered
