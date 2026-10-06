"""Small, entirely synthetic EPUB fixtures shared across the test suite."""

from __future__ import annotations

from html import escape
import os
import random
from pathlib import Path
import struct
import zlib
from zipfile import ZIP_STORED, ZipFile

import pytest
from urllib.request import OpenerDirector, Request

from econ_digest.epub_parser import parse_epub
from econ_digest.models import Article, Issue


@pytest.fixture(autouse=True)
def offline_analysis_research(monkeypatch: pytest.MonkeyPatch) -> None:
    from econ_digest.analysis import pipeline
    from econ_digest.research.cna import CNAClient
    from econ_digest.research import http
    from types import SimpleNamespace

    def offline_open(*args, **kwargs):
        raise OSError("synthetic offline evidence")

    monkeypatch.setattr(http, "build_opener", lambda *args: SimpleNamespace(open=offline_open))

    original_init = CNAClient.__init__

    def offline_init(self, *args, **kwargs):
        kwargs.setdefault("sleep", lambda _: None)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(CNAClient, "__init__", offline_init)

    class OfflineCNA(CNAClient):
        def search(self, query: str):
            return []

    monkeypatch.setattr(pipeline, "CNAClient", OfflineCNA)


@pytest.fixture(autouse=True)
def disable_live_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delivery tests must inject fake openers and never publish real pages."""
    original = OpenerDirector.open

    def guarded_open(self: OpenerDirector, fullurl: Request | str, *args: object, **kwargs: object):
        url = fullurl.full_url if isinstance(fullurl, Request) else fullurl
        if url.startswith(("http://", "https://")):
            pytest.fail("測試禁止連線；請使用假 opener")
        return original(self, fullurl, *args, **kwargs)

    monkeypatch.setattr(OpenerDirector, "open", guarded_open)


@pytest.fixture(autouse=True)
def disable_live_gwg(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """A newly implemented command must never spend live quota during pytest."""
    if os.environ.get("ECON_DIGEST_LIVE_GWG") == "1":
        return
    directory = tmp_path_factory.mktemp("quota-guard")
    executable = directory / "gwg"
    executable.write_text(
        '#!/bin/sh\n'
        'printf \'%s\\n\' \'{"status":"ERROR","error":"live gwg disabled in tests","response":""}\'\n'
        'exit 2\n', encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ.get("PATH", ""))


@pytest.fixture
def synthetic_epub(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.epub"

    def article(
        section: str, title: str, body: str, fly: str | None = "Synthetic fly title",
        rubric: str | None = "A synthetic rubric", date: bool = True,
    ) -> str:
        fly_html = f'<span class="te_fly_span"> | {escape(fly)}</span>' if fly else ""
        rubric_html = f'<h3 class="te_article_rubric">{escape(rubric)}</h3>' if rubric else ""
        date_html = '<span class="te_article_datePublished">Oct 1st 2026</span><br/>' if date else ""
        return f'''<html><body><p><span class="te_section_title">{escape(section)}</span>{fly_html}</p>
        <h1 class="other te_article_title">{escape(title)} </h1>{rubric_html}
        <p><img class="te_head_image" src="photo.jpg"/></p><hr/>{date_html}{body}
        <p class="link_navbar"><a href="https://example.invalid">Navigation only</a></p></body></html>'''

    files = {
        "normal": article("Finance & economics", "Synthetic firms & markets", '<p>One &amp; two <a href="https://example.invalid/ignored">linked words</a> remain.</p><p>Typographic “quotes” and readers’ choices.</p><p>  </p><p><img src="chart.jpg"/></p>'),
        "no-metadata": article("Business", "A plain synthetic story", '<p>Body without date and metadata.</p>', fly=None, rubric=None, date=False),
        "chaguan": article("China", "A synthetic column", '<p>Taiwan and TSMC make synthetic chips.</p>', fly="Chaguan"),
        "cover-leader": article("Leaders", "A synthetic cover argument", '<p>An invented argument for a cover.</p>', fly="Our cover"),
        "politics": article("The world this week", "Politics", '<p></p><p>A synthetic political brief.</p><p>Another invented political brief.</p>', fly=None, rubric=None),
        "business": article("The world this week", "Business", '<p></p><p>A synthetic business brief.</p>', fly=None),
        "cartoon": article("The world this week", "Cartoon: A fictional drawing", '<p>An invented caption.</p>', fly=None),
        "letters": article("Letters", "Synthetic correspondence", '<p>A reader writes an invented letter.</p><p>Letters are welcome via email at example.invalid.</p>'),
        "non-article": '<html><body><h1>Contents</h1><p>This is not an article.</p></body></html>',
    }
    groups = [
        ("Front matter", ["non-article"]), ("Finance & economics", ["normal"]),
        ("Business", ["no-metadata"]), ("China", ["chaguan"]),
        ("Leaders", ["cover-leader"]), ("The world this week", ["politics", "business", "cartoon"]),
        ("Letters", ["letters"]),
    ]
    nav = '<html><body><nav epub:type="toc"><ol>' + "".join(
        f'<li><span>{escape(section)}</span><ol>' + "".join(
            f'<li><a href="{name}.html">Synthetic navigation title</a></li>' for name in names
        ) + "</ol></li>" for section, names in groups
    ) + "</ol></nav></body></html>"
    spine_ids = [name for _, names in groups for name in names]
    opf = '<package xmlns="http://www.idpf.org/2007/opf"><manifest>' + "".join(
        f'<item id="{name}" href="{name}.html" media-type="application/xhtml+xml"/>' for name in files
    ) + '</manifest><spine>' + "".join(f'<itemref idref="{name}"/>' for name in spine_ids) + '</spine></package>'
    with ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="EPUB/content.opf"/></rootfiles></container>')
        archive.writestr("EPUB/nav.xhtml", nav)
        archive.writestr("EPUB/content.opf", opf)
        for name, html in files.items():
            archive.writestr(f"EPUB/{name}.html", html)
    return path


@pytest.fixture
def epub_path(synthetic_epub: Path) -> Path:
    return synthetic_epub


@pytest.fixture
def synthetic_issue(synthetic_epub: Path) -> Issue:
    return parse_epub(synthetic_epub, "2026.10.03", "https://example.invalid/synthetic.epub")


@pytest.fixture
def synthetic_article(synthetic_issue: Issue) -> Article:
    return synthetic_issue.articles[0]


@pytest.fixture
def synthetic_pngs() -> dict[str, bytes]:
    """Valid, generated raster bytes; no copyrighted test assets."""
    def png(seed: int, size: int = 32) -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        rng = random.Random(seed)
        rows = b"".join(b"\0" + rng.randbytes(size * 3) for _ in range(size))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return {**{name: png(index) for index, name in enumerate(("cover", "head", "inline", "leader", "promo"))},
            "small": png(9, 1)}


@pytest.fixture
def illustrated_epub(synthetic_epub: Path, synthetic_pngs: dict[str, bytes], tmp_path: Path) -> Path:
    path = tmp_path / "illustrated.epub"
    with ZipFile(synthetic_epub) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    opf = contents["EPUB/content.opf"].decode()
    opf = opf.replace("<manifest>", '<metadata><meta name="cover" content="cover-img"/></metadata><manifest>')
    opf = opf.replace("</manifest>", "".join(
        f'<item id="{name}-img" href="static_images/{name}.png" media-type="image/png"'
        + (' properties="cover-image"' if name == "cover" else "") + "/>"
        for name in synthetic_pngs) + '</manifest>')
    # A nested article exercises ../ resolution and encoded filenames.
    opf = opf.replace('href="normal.html"', 'href="articles/normal.html"')
    contents["EPUB/content.opf"] = opf.encode()
    for name in list(contents):
        if not name.endswith(".html"):
            continue
        html = contents[name].decode().replace("photo.jpg", "static_images/head.png").replace("chart.jpg", "static_images/inline.png")
        if name.endswith("cover-leader.html"):
            html = html.replace("static_images/head.png", "static_images/leader.png")
        if name.endswith("normal.html"):
            html = html.replace("<body>", '<body><p><img src="static_images/inline.png"/></p>')
            html = html.replace("</body>", '<img src="static_images/head.png"/><img src="static_images/small.png"/>'
                                '<img src="static_images/mastheadImage.jpg"/><img src="static_images/ereader.png"/>'
                                '<img src="missing.png"/><img src="https://example.invalid/external.png"/></body>')
            html = html.replace("static_images/", "../static_images/").replace("head.png", "he%61d.png")
            del contents[name]
            name = "EPUB/articles/normal.html"
        contents[name] = html.encode()
    for name, data in synthetic_pngs.items():
        contents[f"EPUB/static_images/{name}.png"] = data
    contents["EPUB/static_images/mastheadImage.jpg"] = synthetic_pngs["promo"]
    contents["EPUB/static_images/ereader.png"] = synthetic_pngs["promo"]
    with ZipFile(path, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    return path
