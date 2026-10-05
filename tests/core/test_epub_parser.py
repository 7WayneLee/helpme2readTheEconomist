from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from econ_digest.epub_parser import EpubParseError, parse_epub
from econ_digest.models import Issue


def test_article_order_and_issue_metadata(synthetic_issue: Issue) -> None:
    assert [article.id for article in synthetic_issue.articles] == [
        "normal", "no-metadata", "chaguan", "cover-leader", "politics", "business", "cartoon", "letters",
    ]
    assert [article.order for article in synthetic_issue.articles] == list(range(8))
    assert synthetic_issue.issue_date == "2026.10.03"
    assert synthetic_issue.source_url.endswith("synthetic.epub")
    assert synthetic_issue.fetched_at.endswith("+00:00")


def test_article_fields_and_body_filtering(synthetic_issue: Issue) -> None:
    article = synthetic_issue.articles[0]
    assert article.section == "Finance & economics"
    assert article.title == "Synthetic firms & markets"
    assert article.fly_title == "Synthetic fly title"
    assert article.rubric == "A synthetic rubric"
    assert article.date_published == "Oct 1st 2026"
    assert article.paragraphs == [
        "One & two linked words remain.", "Typographic “quotes” and readers’ choices.",
    ]
    assert article.word_count == 11
    assert article.kind == "article"
    assert not article.is_cover


def test_missing_metadata_and_date_fallback(synthetic_issue: Issue) -> None:
    article = synthetic_issue.articles[1]
    assert article.fly_title is None
    assert article.rubric is None
    assert article.date_published is None
    assert article.paragraphs == ["Body without date and metadata."]
    assert article.word_count == 5


def test_kinds_cover_briefs_and_letters(synthetic_issue: Issue) -> None:
    assert [article.kind for article in synthetic_issue.articles] == [
        "article", "article", "column", "leader", "world_politics", "world_business", "cartoon", "letters",
    ]
    assert synthetic_issue.articles[3].is_cover
    assert synthetic_issue.articles[4].paragraphs == ["A synthetic political brief.", "Another invented political brief."]
    assert synthetic_issue.articles[7].paragraphs == ["A reader writes an invented letter."]
    assert all(article.word_count == sum(len(p.split()) for p in article.paragraphs) for article in synthetic_issue.articles)


def test_opf_spine_fallback(synthetic_epub: Path, tmp_path: Path) -> None:
    target = tmp_path / "without-nav.epub"
    with ZipFile(synthetic_epub) as source, ZipFile(target, "w") as archive:
        for name in source.namelist():
            if name != "EPUB/nav.xhtml":
                archive.writestr(name, source.read(name))
    issue = parse_epub(target, "2026.10.03", "synthetic")
    assert len(issue.articles) == 8
    assert issue.articles[0].id == "normal"
    assert issue.articles[0].section == "Finance & economics"


def test_nested_nav_sections_and_fragments(synthetic_epub: Path, tmp_path: Path) -> None:
    target = tmp_path / "nested-nav.epub"
    nav = '<nav epub:type="toc"><ol><li><span>Outer</span><ol><li><span>Inner &amp; nested</span><ol><li><a href="normal.html#top">A</a></li><li><a href="normal.html#second">Duplicate</a></li></ol></li></ol></li></ol></nav>'
    with ZipFile(synthetic_epub) as source, ZipFile(target, "w") as archive:
        for name in source.namelist():
            content = source.read(name)
            if name == "EPUB/nav.xhtml":
                content = nav.encode()
            elif name == "EPUB/normal.html":
                content = content.replace(b'te_section_title', b'ignored_section_class')
            archive.writestr(name, content)
    issue = parse_epub(target, "2026.10.03", "synthetic")
    assert len(issue.articles) == 1
    assert issue.articles[0].section == "Inner & nested"


def test_invalid_epub_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "bad.epub"
    path.write_text("not a zip")
    with pytest.raises(EpubParseError):
        parse_epub(path, "2026.10.03", "synthetic")
