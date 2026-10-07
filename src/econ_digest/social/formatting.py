"""Chinese-only article posts, with whole-sentence length budgeting."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from ..config import ThreadsConfig
from ..models import Digest
from ..render.common import Entry, clean_text, overview, title

LIMIT = 500
_URL = re.compile(r"https?://[^\s）)<>]+")
_SENTENCE = re.compile(r".+?[。！？!?][」』”]*|.+$", re.DOTALL)


class FormatError(ValueError):
    """Required text cannot fit without losing its meaning or links."""


def character_count(text: str) -> int:
    """Meta: characters, except emoji counted in UTF-8 bytes.

    Meta does not publish an exhaustive emoji table. Count symbols, non-BMP
    characters, emoji selectors/joiners/keycaps conservatively in UTF-8 bytes.
    Chinese and normal punctuation each use one unit; URLs use their full length.
    This may overcount rare non-emoji symbols, but never grants extra space.
    """
    return sum(len(char.encode("utf-8")) if (
        unicodedata.category(char) == "So" or ord(char) > 0xFFFF
        or char in "\ufe0f\ufe0e\u200d\u20e3"
    ) else 1 for char in text)


@dataclass(frozen=True)
class Post:
    key: str
    issue_date: str
    article_id: str
    section: str
    text: str
    link_url: str
    image_url: str | None = None
    topic_tag: str = ""


def _protected(text: str) -> bool:
    return "（推論）" in text or bool(_URL.search(text))


def _shorter(text: str) -> str | None:
    sentences = _SENTENCE.findall(text)
    if len(sentences) < 2:
        return None
    candidate = "".join(sentences[:-1]).strip()
    # Inference qualifications and Taiwan source URLs are indivisible.
    if text.count("（推論）") != candidate.count("（推論）"):
        return None
    if any(url not in candidate for url in _URL.findall(text)):
        return None
    return candidate or None


def _fit(heading: str, headline: str, points: list[str], context: list[str],
         link_url: str) -> str:
    def compose() -> str:
        body = [headline, *["・" + point for point in points], *context]
        return "\n\n".join([heading, "\n".join(body), link_url])

    while character_count(compose()) > LIMIT:
        # Drop whole optional points before shortening any prose.
        removable = next((i for i in range(len(points) - 1, -1, -1)
                          if not _protected(points[i])), None)
        if removable is not None:
            points.pop(removable)
            continue
        # Preserve the site title, links and inference qualifications.
        shorter = _shorter(headline)
        if shorter is not None:
            headline = shorter
            continue
        changed = False
        for collection in (points, context):
            for i in range(len(collection) - 1, -1, -1):
                shorter = _shorter(collection[i])
                if shorter is not None:
                    collection[i] = shorter
                    changed = True
                    break
            if changed:
                break
        if not changed:
            raise FormatError("必要內容超過 Threads 500 字元；請縮短中文摘要，保留標題、推論標示與台灣連結。")
    return compose()


def article_post(digest: Digest, entry: Entry, section: str, link_url: str,
                 config: ThreadsConfig) -> Post:
    heading = clean_text(entry.classification.title_zh)
    if entry.classification.taiwan_level:
        heading = "【台灣】" + heading
    summary = entry.summary
    points = list(summary.key_points[:3]) if summary.tier in "ABC" else []
    # A/B summaries often use the argument contract instead of key_points.
    if summary.tier in "ABC" and len(points) < 2 and summary.argument:
        points = [summary.argument.claim, *summary.argument.evidence][:3]
    if summary.tier in "ABC" and len(points) < 2:
        points = list(dict.fromkeys([*points, *summary.key_data]))[:3]
    context = []
    if entry.classification.taiwan_link:
        context.append("與台灣的關聯：" + clean_text(entry.classification.taiwan_link))
    text = _fit(heading, clean_text(summary.headline_zh), [clean_text(p) for p in points],
                context, link_url)
    return Post(f"{digest.issue_date}:{entry.article.id}", digest.issue_date,
                entry.article.id, section, text, link_url, topic_tag=config.topic_tag)


def intro_post(digest: Digest, link_url: str, image_url: str | None,
               config: ThreadsConfig) -> Post:
    text = "\n".join([title(digest), overview(digest), "", link_url])
    if character_count(text) > LIMIT:
        raise FormatError("本期介紹超過 Threads 500 字元。")
    return Post(f"{digest.issue_date}:intro", digest.issue_date, "intro", "本週導讀", text,
                link_url, image_url, config.topic_tag)
