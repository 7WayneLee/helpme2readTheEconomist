import base64
from pathlib import Path
import shutil

import pytest

from econ_digest.commands import render
from econ_digest.config import Config, PathsConfig, ReportConfig
from econ_digest.images import load_issue_images
from econ_digest.models import Digest, save_json
from econ_digest.render import render_html, render_markdown
from econ_digest.cli import build_parser


def encoded(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


def test_private_report_embedding_order(sample_digest: Digest, illustrated_epub: Path, synthetic_pngs: dict[str, bytes]) -> None:
    images = load_issue_images(illustrated_epub)
    images.by_article["sample-1"] = images.by_article["normal"]
    images.by_article["sample-2"] = images.by_article["no-metadata"]
    report = render_html(sample_digest, images)
    cover = encoded(synthetic_pngs["cover"])
    assert report.index("</h1>") < report.index(cover) < report.index("產生時間：")
    assert '<figure class="issue-cover">' in report
    stories = report.split('<article class="story">')[1:]
    first = stories[0].split("</article>")[0]
    assert first.index(encoded(synthetic_pngs["head"])) < first.index("一句話重點")
    assert first.index("文章脈絡") < first.index(encoded(synthetic_pngs["inline"])) < first.index("</details>")
    assert first.index(encoded(synthetic_pngs["head"])) < first.index(encoded(synthetic_pngs["inline"]))
    assert 'alt="台灣晶片展望 插圖" loading="lazy"' in first
    second = stories[1].split("</article>")[0]
    assert encoded(synthetic_pngs["head"]) in second
    assert encoded(synthetic_pngs["leader"]) not in second
    assert "社論" not in second
    brief = report.split('<section id="brief">')[1].split("</section>")[0]
    politics = brief.split("<h3>政治</h3>")[1].split("<h3>商業</h3>")[0]
    business = brief.split("<h3>商業</h3>")[1].split("<h3>本週漫畫</h3>")[0]
    for section in (politics, business):
        assert section.index("<figure>") < section.rindex("</li>")
        assert "▲ 配圖：" in section
    assert '<h3>本週漫畫</h3><figure><img' in brief
    assert 'alt="本週漫畫 插圖"' in brief
    assert "max-width:100%" in report and "height:auto" in report and "max-height:60vh" in report
    assert "data:image" not in render_markdown(sample_digest)


def test_illustration_alt_text_escaped(sample_digest: Digest, illustrated_epub: Path) -> None:
    images = load_issue_images(illustrated_epub)
    images.by_article["sample-1"] = images.by_article["normal"]
    sample_digest.classifications["sample-1"].title_zh = '測試 " < &'
    assert 'alt="測試 &quot; &lt; &amp; 插圖"' in render_html(sample_digest, images)


@pytest.mark.parametrize("enabled,exists", [(True, True), (False, True), (True, False)])
def test_render_command_honors_image_config(sample_digest: Digest, illustrated_epub: Path, tmp_path: Path,
                                          enabled: bool, exists: bool) -> None:
    config = Config(paths=PathsConfig(tmp_path, tmp_path / "output"), report=ReportConfig(embed_images=enabled))
    directory = tmp_path / "issues" / "te_2026.10.03"
    save_json(directory / "digest.json", sample_digest)
    if exists:
        shutil.copyfile(illustrated_epub, directory / "TheEconomist.2026.10.03.epub")
    args = build_parser().parse_args(["render", "--issue", "2026.10.03"])
    assert render.run(args, config) == 0
    report = (directory / "report.html").read_text()
    assert ("data:image" in report) == (enabled and exists)
    assert (directory / "report.md").read_text() == render_markdown(sample_digest)
    if not (enabled and exists):
        assert report == render_html(sample_digest)
