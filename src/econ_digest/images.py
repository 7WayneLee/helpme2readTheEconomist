"""Load private report illustrations directly from an EPUB archive."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import mimetypes
from pathlib import Path, PurePosixPath
import posixpath
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from .epub_parser import _Document, _parse_article, article_paragraph_nodes


@dataclass(frozen=True)
class ImageBlob:
    name: str
    mime: str
    data: bytes


@dataclass(frozen=True)
class PositionedImage:
    image: ImageBlob
    before_paragraph: int


@dataclass
class ArticleImages:
    head: ImageBlob | None = None
    inline: list[PositionedImage] = field(default_factory=list)


@dataclass
class IssueImages:
    cover: ImageBlob | None = None
    by_article: dict[str, ArticleImages] = field(default_factory=dict)


class _Tags(HTMLParser):
    def __init__(self, document: bytes) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.feed(document.decode("utf-8-sig", errors="replace"))
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag.rsplit(":", 1)[-1], {key: value or "" for key, value in attrs}))


def _resolve(base: str, source: str) -> str | None:
    parts = urlsplit(source)
    if parts.scheme or parts.netloc or not parts.path:
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(parts.path)))
    return None if path.startswith(("/", "../")) else path


def load_issue_images(epub_path: str | Path) -> IssueImages:
    """Keep the cover and article images; never fetch external references."""
    result = IssueImages()
    with ZipFile(epub_path) as archive:
        names = set(archive.namelist())
        roots = (_Tags(archive.read("META-INF/container.xml")).tags
                 if "META-INF/container.xml" in names else [])
        opf = next((attrs.get("full-path") for tag, attrs in roots
                    if tag == "rootfile" and attrs.get("full-path") in names), None)
        if opf is None:
            opf = next((name for name in archive.namelist() if name.endswith(".opf")), None)
        if opf is None:
            return result
        tags = _Tags(archive.read(opf)).tags
        items = [attrs for tag, attrs in tags if tag == "item"]
        media = {path: item.get("media-type", "") for item in items
                 if (path := _resolve(opf, item.get("href", ""))) is not None}

        def image(path: str | None) -> ImageBlob | None:
            if path is None or path not in names:
                return None
            stem = PurePosixPath(path).stem.casefold()
            if stem in {"mastheadimage", "ereader"}:
                return None
            mime = media.get(path) or mimetypes.guess_type(path)[0] or ""
            if not mime.startswith("image/"):
                return None
            data = archive.read(path)
            return ImageBlob(path, mime, data) if len(data) >= 2048 else None

        cover_id = next((attrs.get("content") for tag, attrs in tags
                         if tag == "meta" and attrs.get("name") == "cover"), None)
        covers = [item for item in items if "cover-image" in item.get("properties", "").split()]
        covers.extend(item for item in items if item.get("id") == cover_id and item not in covers)
        result.cover = next((blob for item in covers
                             if (blob := image(_resolve(opf, item.get("href", "")))) is not None), None)
        for item in items:
            html_path = _resolve(opf, item.get("href", ""))
            if html_path not in names or not (item.get("media-type") in {"application/xhtml+xml", "text/html"}
                                             or PurePosixPath(html_path).suffix in {".html", ".xhtml", ".htm"}):
                continue
            html = archive.read(html_path).decode("utf-8-sig", errors="replace")
            article = _parse_article(html, html_path, 0, "")
            if article is None:
                continue
            nodes = list(_Document(html).root.walk())
            title_node = next(n for n in nodes if n.tag == "h1" and n.has_class("te_article_title"))
            date_node = next((n for n in nodes if n.has_class("te_article_datePublished")), None)
            paragraphs = article_paragraph_nodes(nodes, (date_node or title_node).position, article.kind)
            refs = [n for n in nodes if n.tag == "img" and (n.has_class("te_head_image") or n.position > (date_node or title_node).position)]
            # Prefer designated head references before deduplicating reused files.
            refs.sort(key=lambda n: not n.has_class("te_head_image"))
            seen: set[str] = set()
            selected = ArticleImages()
            for ref in refs:
                path = _resolve(html_path, ref.attrs.get("src", ""))
                if path in seen:
                    continue
                if (blob := image(path)) is not None:
                    seen.add(blob.name)
                    if ref.has_class("te_head_image") and selected.head is None:
                        selected.head = blob
                    else:
                        position = sum(n.position < ref.position for n in paragraphs)
                        selected.inline.append(PositionedImage(blob, position))
            selected.inline.sort(key=lambda item: item.before_paragraph)
            if selected.head or selected.inline:
                result.by_article[PurePosixPath(html_path).stem] = selected
    return result
