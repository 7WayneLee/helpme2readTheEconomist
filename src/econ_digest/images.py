"""Load private report illustrations directly from an EPUB archive."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import mimetypes
from pathlib import Path, PurePosixPath
import posixpath
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile


@dataclass(frozen=True)
class ImageBlob:
    name: str
    mime: str
    data: bytes


@dataclass
class IssueImages:
    cover: ImageBlob | None = None
    by_article: dict[str, list[ImageBlob]] = field(default_factory=dict)


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
            refs = [attrs for tag, attrs in _Tags(archive.read(html_path)).tags if tag == "img"]
            refs.sort(key=lambda attrs: "te_head_image" not in attrs.get("class", "").split())
            seen: set[str] = set()
            blobs = []
            for attrs in refs:
                path = _resolve(html_path, attrs.get("src", ""))
                if path in seen:
                    continue
                if (blob := image(path)) is not None:
                    seen.add(blob.name)
                    blobs.append(blob)
            if blobs:
                result.by_article[PurePosixPath(html_path).stem] = blobs
    return result
