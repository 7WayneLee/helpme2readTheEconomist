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
from econ_digest.site.build import build_site


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


@pytest.mark.parametrize("kind,label", [("chart", "圖表"), ("map", "地圖"),
                                       ("photo", "配圖"), ("illustration", "配圖")])
def test_inline_caption_and_alt_in_report_and_site(sample_digest: Digest, illustrated_epub: Path,
                                                 tmp_path: Path, kind: str, label: str) -> None:
    images = load_issue_images(illustrated_epub)
    images.by_article["sample-1"] = images.by_article["normal"]
    blob = images.by_article["sample-1"].inline[0].image
    description = '合成圖片 "甲" 與 <乙> & 背景。'
    sample_digest.figure_notes[blob.name] = {"kind": kind, "description_zh": description}
    report = render_html(sample_digest, images)
    built = build_site(sample_digest, tmp_path / "site", images=images)
    site = built.pages["taiwan"].read_text()
    for html in (report, site):
        assert f'<figcaption>▲ {label}：合成圖片 &quot;甲&quot; 與 &lt;乙&gt; &amp; 背景。</figcaption>' in html
        assert 'alt="合成圖片 &quot;甲&quot; 與 &lt;乙&gt; &amp; 背景。" loading="lazy"' in html
        story = html.split('<article class="story">')[1].split("</article>")[0]
        assert story.index("文章脈絡") < story.index("<figcaption>") < story.index("</details>")
        assert story.index('alt="台灣晶片展望 插圖"') < story.index("閱讀摘要")


@pytest.mark.parametrize("kind,label", [("chart", "圖表"), ("map", "地圖"),
                                       ("photo", "配圖"), ("illustration", "配圖")])
def test_short_alt_and_takeaway_first_captions(sample_digest, illustrated_epub, tmp_path, kind, label):
    images = load_issue_images(illustrated_epub)
    images.by_article["sample-1"] = images.by_article["normal"]
    blob = images.by_article["sample-1"].inline[0].image
    sample_digest.figure_notes[blob.name] = {
        "kind": kind, "alt_zh": '配圖："A" <乙> & 背景',
        "takeaway_zh": '甲地區的比率明顯高於乙地區。',
        "description_zh": '長條圖比較兩個地區在 2025 年的比率，單位為百分比。來源：合成資料。'}
    for html in (render_html(sample_digest, images),
                 build_site(sample_digest, tmp_path / "site", images=images).pages["taiwan"].read_text()):
        assert 'alt="配圖：&quot;A&quot; &lt;乙&gt; &amp; 背景" loading="lazy"' in html
        if kind in {"chart", "map"}:
            assert (f'<figcaption>▲ {label}｜重點：甲地區的比率明顯高於乙地區。　'
                    '長條圖比較兩個地區在 2025 年的比率，單位為百分比。來源：合成資料。</figcaption>') in html
        else:
            assert '<figcaption>▲ 配圖：長條圖比較兩個地區在 2025 年的比率，單位為百分比。來源：合成資料。</figcaption>' in html
            assert '重點：甲地區' not in html


@pytest.mark.parametrize("kind,label", [("chart", "圖表"), ("map", "地圖")])
@pytest.mark.parametrize("takeaway", [None, 42, "甲" * 9, "甲" * 61])
def test_chart_without_valid_takeaway_renders_description(sample_digest, illustrated_epub, tmp_path,
                                                        kind, label, takeaway):
    images = load_issue_images(illustrated_epub)
    images.by_article["sample-1"] = images.by_article["normal"]
    blob = images.by_article["sample-1"].inline[0].image
    note = {"kind": kind, "alt_zh": "圖表：合成地區比較", "description_zh": "甲" * 20}
    if takeaway is not None:
        note["takeaway_zh"] = takeaway
    sample_digest.figure_notes[blob.name] = note
    for html in (render_html(sample_digest, images),
                 build_site(sample_digest, tmp_path / "site", images=images).pages["taiwan"].read_text()):
        assert f'<figcaption>▲ {label}｜' + "甲" * 20 + '</figcaption>' in html
        assert 'alt="圖表：合成地區比較"' in html
        assert '重點：' not in html


@pytest.mark.parametrize("bad_field", [
    {"kind": "unknown"}, {"alt_zh": "短"}, {"alt_zh": 42},
    {"description_zh": "甲" * 141}, {"description_zh": None}])
def test_invalid_new_note_keeps_image_without_caption(sample_digest, illustrated_epub, tmp_path, bad_field):
    images = load_issue_images(illustrated_epub)
    images.by_article["sample-1"] = images.by_article["normal"]
    blob = images.by_article["sample-1"].inline[0].image
    sample_digest.figure_notes[blob.name] = {
        "kind": "chart", "alt_zh": "圖表：合成地區比較", "description_zh": "甲" * 20, **bad_field}
    for html in (render_html(sample_digest, images),
                 build_site(sample_digest, tmp_path / "site", images=images).pages["taiwan"].read_text()):
        story = html.split('<article class="story">')[1].split("</article>")[0]
        assert story.count('<figure>') == 2 and '<figcaption>' not in story
        assert story.count('alt="台灣晶片展望 插圖"') == 2


def test_legacy_long_chart_description_still_renders(sample_digest, illustrated_epub):
    images = load_issue_images(illustrated_epub)
    images.by_article["sample-1"] = images.by_article["normal"]
    blob = images.by_article["sample-1"].inline[0].image
    sample_digest.figure_notes[blob.name] = {"kind": "chart", "description_zh": "甲" * 180}
    html = render_html(sample_digest, images)
    assert '<figcaption>▲ 圖表：' + "甲" * 180 + '</figcaption>' in html
    assert 'alt="' + "甲" * 180 + '"' in html


def test_no_note_preserves_inline_image_without_caption(sample_digest: Digest, illustrated_epub: Path,
                                                       tmp_path: Path) -> None:
    images = load_issue_images(illustrated_epub)
    images.by_article["sample-1"] = images.by_article["normal"]
    site = build_site(sample_digest, tmp_path / "site", images=images).pages["taiwan"].read_text()
    for html in (render_html(sample_digest, images), site):
        story = html.split('<article class="story">')[1].split("</article>")[0]
        assert story.count('<figure>') == 2
        assert "<figcaption>" not in story
        assert story.count('alt="台灣晶片展望 插圖"') == 2


def test_tier_c_taiwan_summary_is_open_but_level_zero_is_closed(sample_digest: Digest, tmp_path: Path) -> None:
    report = render_html(sample_digest)
    built = build_site(sample_digest, tmp_path / "site")
    taiwan = built.pages["taiwan"].read_text()
    world = built.pages["world"].read_text()
    for html in (report, taiwan):
        story = html.split('<h4>供應鏈間接影響</h4>')[1].split("</article>")[0]
        assert '<details open><summary>閱讀摘要</summary>' in story
    for html in (report, world):
        story = html.split('<h4>美國政策</h4>')[1].split("</article>")[0]
        assert '<details><summary>閱讀摘要</summary>' in story
        assert '<details open>' not in story


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
