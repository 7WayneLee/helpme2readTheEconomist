"""Read EPUB navigation and article HTML without third-party parsers."""

from __future__ import annotations

import posixpath
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Iterator
from xml.etree import ElementTree

from .models import Article, Issue
from .taxonomy import derive_kind


class EpubParseError(ValueError):
    """The EPUB container or reading order is invalid."""


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    position: int
    children: list[_Node | str] = field(default_factory=list)

    def walk(self) -> Iterator[_Node]:
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.walk()

    def text(self) -> str:
        return "".join(child.text() if isinstance(child, _Node) else child for child in self.children)

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()


class _Document(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {}, 0)
        self.stack = [self.root]
        self.position = 0
        self.feed(html)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.position += 1
        node = _Node(tag, {key: value or "" for key, value in attrs}, self.position)
        self.stack[-1].children.append(node)
        if tag == "br":
            node.children.append(" ")
        if tag not in self._VOID:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _text(node: _Node | None) -> str | None:
    if node is None:
        return None
    return " ".join(node.text().split()) or None


def _href_path(base: str, href: str) -> str | None:
    parts = urllib.parse.urlsplit(href)
    if parts.scheme or parts.netloc or not parts.path:
        return None
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), urllib.parse.unquote(parts.path)))


def _nav_order(archive: zipfile.ZipFile, nav_path: str) -> list[tuple[str, str]]:
    document = _Document(archive.read(nav_path).decode("utf-8-sig"))
    navs = [node for node in document.root.walk() if node.tag == "nav"]
    nav = next((node for node in navs if "toc" in node.attrs.get("epub:type", "").split()), navs[0] if navs else document.root)
    result: list[tuple[str, str]] = []

    def visit(node: _Node, section: str) -> None:
        if node.tag == "li":
            heading = next((child for child in node.children if isinstance(child, _Node) and child.tag == "span"), None)
            section = _text(heading) or section
        if node.tag == "a":
            path = _href_path(nav_path, node.attrs.get("href", ""))
            if path:
                result.append((path, section))
        for child in node.children:
            if isinstance(child, _Node):
                visit(child, section)

    visit(nav, "")
    return result


def _spine_order(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    try:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        opf_path = rootfile.attrib["full-path"] if rootfile is not None else ""
    except KeyError:
        opf_path = ""
    if not opf_path:
        opf_path = next((name for name in archive.namelist() if name.endswith(".opf")), "")
    if not opf_path:
        raise EpubParseError("EPUB 沒有導覽檔或 OPF 閱讀順序")
    opf = ElementTree.fromstring(archive.read(opf_path))
    manifest = {item.attrib["id"]: item.attrib.get("href", "") for item in opf.findall(".//{*}manifest/{*}item")}
    result: list[tuple[str, str]] = []
    for itemref in opf.findall(".//{*}spine/{*}itemref"):
        href = manifest.get(itemref.attrib.get("idref", ""), "")
        path = _href_path(opf_path, href)
        if path:
            result.append((path, ""))
    return result


def _parse_article(html: str, path: str, order: int, nav_section: str) -> Article | None:
    nodes = list(_Document(html).root.walk())

    def by_class(name: str) -> _Node | None:
        return next((node for node in nodes if node.has_class(name)), None)

    title_node = next((node for node in nodes if node.tag == "h1" and node.has_class("te_article_title")), None)
    if title_node is None:
        return None
    title = _text(title_node) or ""
    section = _text(by_class("te_section_title")) or nav_section
    fly_title = _text(by_class("te_fly_span"))
    if fly_title:
        fly_title = fly_title.lstrip("| ").strip() or None
    date_node = by_class("te_article_datePublished")
    threshold = date_node.position if date_node else title_node.position
    kind = derive_kind(section, title, fly_title)
    paragraphs: list[str] = []
    for node in nodes:
        if node.tag != "p" or node.position <= threshold or node.has_class("link_navbar"):
            continue
        if any(child.has_class("te_section_title") or child.has_class("te_fly_span") for child in node.walk()):
            continue
        paragraph = _text(node)
        if not paragraph:
            continue
        if kind == "letters" and paragraph.casefold().startswith("letters are welcome via email"):
            continue
        paragraphs.append(paragraph)
    return Article(
        id=PurePosixPath(path).stem, order=order, section=section, fly_title=fly_title,
        title=title, rubric=_text(by_class("te_article_rubric")),
        date_published=_text(date_node), paragraphs=paragraphs,
        word_count=sum(len(paragraph.split()) for paragraph in paragraphs), kind=kind,
        is_cover=kind == "leader" and (fly_title or "").casefold() == "our cover",
    )


def parse_epub(path: str | Path, issue_date: str, source_url: str) -> Issue:
    epub_path = Path(path)
    articles: list[Article] = []
    try:
        with zipfile.ZipFile(epub_path) as archive:
            names = set(archive.namelist())
            nav_path = "EPUB/nav.xhtml" if "EPUB/nav.xhtml" in names else next((name for name in archive.namelist() if name.endswith("/nav.xhtml") or name == "nav.xhtml"), "")
            order = _nav_order(archive, nav_path) if nav_path else []
            if not order:
                order = _spine_order(archive)
            seen: set[str] = set()
            for article_path, section in order:
                if article_path in seen:
                    continue
                seen.add(article_path)
                if article_path not in names:
                    raise EpubParseError(f"EPUB 導覽參照不存在的檔案：{article_path}")
                article = _parse_article(
                    archive.read(article_path).decode("utf-8-sig"), article_path, len(articles), section,
                )
                if article:
                    articles.append(article)
    except (zipfile.BadZipFile, ElementTree.ParseError, UnicodeError, KeyError, OSError) as exc:
        raise EpubParseError("無法解析 EPUB 容器或內容") from exc
    if not articles:
        raise EpubParseError("EPUB 沒有可解析的文章")
    return Issue(
        issue_date=issue_date, source_url=source_url,
        fetched_at=datetime.fromtimestamp(epub_path.stat().st_mtime, timezone.utc).isoformat(),
        articles=articles,
    )
