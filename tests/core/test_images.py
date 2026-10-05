from pathlib import Path
from zipfile import ZipFile

import pytest

from econ_digest.images import IssueImages, load_issue_images


def test_cover_head_inline_order_and_filters(illustrated_epub: Path, synthetic_pngs: dict[str, bytes]) -> None:
    images = load_issue_images(illustrated_epub)
    assert images.cover is not None
    assert images.cover.name == "EPUB/static_images/cover.png"
    assert images.cover.mime == "image/png" and images.cover.data == synthetic_pngs["cover"]
    assert [blob.name for blob in images.by_article["normal"]] == ["EPUB/static_images/head.png", "EPUB/static_images/inline.png"]
    assert [blob.data for blob in images.by_article["normal"]] == [synthetic_pngs["head"], synthetic_pngs["inline"]]
    assert images.by_article["cover-leader"][0].data == synthetic_pngs["leader"]
    assert "non-article" not in images.by_article


@pytest.mark.parametrize("change", ["metadata", "missing-cover-image", "prefer-property", "no-cover"])
def test_opf_cover_priority_and_fallback(illustrated_epub: Path, tmp_path: Path, change: str) -> None:
    with ZipFile(illustrated_epub) as source:
        contents = {name: source.read(name) for name in source.namelist()}
    opf = contents["EPUB/content.opf"].decode()
    if change == "metadata":
        opf = opf.replace(' properties="cover-image"', "")
    elif change == "missing-cover-image":
        opf = opf.replace(' properties="cover-image"', "")
        opf = opf.replace("</manifest>", '<item id="missing" href="missing.jpg" media-type="image/jpeg" properties="cover-image"/></manifest>')
    elif change == "prefer-property":
        opf = opf.replace('content="cover-img"', 'content="head-img"')
    else:
        opf = opf.replace(' properties="cover-image"', "").replace('name="cover"', 'name="other"')
    contents["EPUB/content.opf"] = opf.encode()
    path = tmp_path / f"{change}.epub"
    with ZipFile(path, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    images = load_issue_images(path)
    if change == "no-cover":
        assert images.cover is None and images.by_article
    else:
        assert images.cover is not None and images.cover.name.endswith("cover.png")


def test_text_only_epub(synthetic_epub: Path) -> None:
    assert load_issue_images(synthetic_epub) == IssueImages()
