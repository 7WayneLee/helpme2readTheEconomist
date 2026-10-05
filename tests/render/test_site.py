from copy import deepcopy
from dataclasses import replace
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess

import pytest

from econ_digest.config import BackupConfig, SiteConfig
from econ_digest.images import ArticleImages, ImageBlob, IssueImages, PositionedImage
from econ_digest.models import ArticleSummary
from econ_digest.render import render_html, render_markdown, render_telegram
from econ_digest.render.common import entries
from econ_digest.render.html import article_html, brief_html
from econ_digest.render.telegraph import render_telegraph, with_navigation
from econ_digest.site import build_site
from econ_digest.site.backup import backup_output
from econ_digest.site.publish import publish_site
from econ_digest.state import load_state


def blobs():
    return [ImageBlob(f"{name}.jpg", "image/jpeg", name.encode() * 2100) for name in ("head", "chart", "late", "leader")]


def test_site_layout_archive_relative_images_epub_navigation(sample_digest, tmp_path, illustrated_epub):
    sample_digest.focus_ids = ["sample-4"]
    sample_digest.summaries["sample-4"].tier = "A"
    site = build_site(sample_digest, tmp_path / "output", illustrated_epub)
    assert list(site.pages) == ["index", "brief", "taiwan", "focus", "world", "topics", "english"]
    assert (site.directory / "TheEconomist.2026.10.03.epub").read_bytes() == illustrated_epub.read_bytes()
    assert (site.root / "assets/site.css").is_file()
    for key, path in site.pages.items():
        html = path.read_text()
        assert f'href="{key}.html" aria-current="page"' in html
        assert "data:image" not in html
        assert 'href="../assets/site.css"' in html
        for other in site.pages:
            assert f'href="{other}.html"' in html
        assert ("← 上一頁" in html) == (key != "index")
        assert ("下一頁 →" in html) == (key != "english")
    index = site.pages["index"].read_text()
    assert index.index('class="issue-cover"') < index.index("<h1>")
    assert "下載本期 epub" in index and '<img src="img/' in index
    assert "美國政策" in site.pages["focus"].read_text()
    assert "美國政策" not in site.pages["world"].read_text()
    guide = site.pages["english"].read_text()
    assert guide.index("閱讀理解") < guide.index("答案（點開）") < guide.index("原文全文")
    assert "[1]" in guide and "[2]" in guide
    older = deepcopy(sample_digest)
    older.issue_date = "2026.09.26"
    build_site(older, site.root, illustrated_epub)
    archive = (site.root / "index.html").read_text()
    assert archive.index("2026-10-03/index.html") < archive.index("2026-09-26/index.html")
    assert archive.count('alt="本期封面"') == 2


def test_site_empty_sections_omitted_and_stale_pages_removed(no_taiwan_digest, tmp_path):
    digest = no_taiwan_digest
    digest.focus_ids = []
    digest.english = None
    digest.week_brief = None
    site = build_site(digest, tmp_path)
    assert set(site.pages) == {"index", "world", "topics"}
    assert not (site.directory / "taiwan.html").exists()
    for path in site.pages.values():
        assert 'href="taiwan.html"' not in path.read_text()
        assert "本期沒有這類文章。" not in path.read_text()
    digest.classifications.clear()
    digest.summaries.clear()
    site = build_site(digest, tmp_path)
    assert set(site.pages) == {"index"}
    assert not (site.directory / "world.html").exists()


def test_head_before_headline_inline_only_deep_analysis_and_ranges(sample_digest):
    head, chart, late, leader = blobs()
    images = IssueImages(by_article={"sample-1": ArticleImages(head, [PositionedImage(chart, 1), PositionedImage(late, 9)]),
                                    "sample-2": ArticleImages(head, [PositionedImage(chart, 1)])})
    sample_digest.summaries["sample-1"].structure = ["第 1 段：起點", "第 2–3 段：中段", "第 4-7 段：最後"]
    first = next(item for item in entries(sample_digest) if item.article.id == "sample-1")
    render = lambda blob, alt, **kwargs: f'<figure>{blob.name}</figure>'
    html = article_html(sample_digest, first, images, render_image=render)
    assert html.index("head.jpg") < html.index("一句話重點")
    assert html.index("第 2–3 段") < html.index("chart.jpg") < html.index("第 4-7 段") < html.index("late.jpg")
    second = next(item for item in entries(sample_digest) if item.article.id == "sample-2")
    assert "head.jpg" in article_html(sample_digest, second, images, render_image=render)
    assert "chart.jpg" not in article_html(sample_digest, second, images, render_image=render)
    first.classification.taiwan_level = 0
    assert "chart.jpg" not in article_html(sample_digest, first, images, render_image=render)
    sample_digest.focus_ids = [first.article.id]
    assert "chart.jpg" in article_html(sample_digest, first, images, render_image=render)
    first.summary.structure = ["未附段落編號"]
    html = article_html(sample_digest, first, images, render_image=render)
    assert html.index("</ol>") < html.index("chart.jpg")


def test_brief_images_follow_their_original_item_even_when_taiwan_sorts_first(sample_digest):
    from econ_digest.models import Article, BriefItem, WeekBrief
    head, chart, *_ = blobs()
    sample_digest.issue.articles.append(Article("political-brief", 100, "The world this week", None, "Politics", None, None, ["a", "b"], 2, "world_politics"))
    sample_digest.week_brief = WeekBrief([BriefItem("普通要聞"), BriefItem("台灣要聞" * 20, True)], [])
    images = IssueImages(by_article={"political-brief": ArticleImages(None, [PositionedImage(chart, 0), PositionedImage(head, 1)])})
    html = brief_html(sample_digest, images, render_image=lambda blob, alt, **kw: f'<figure>{blob.name}<figcaption>{kw["caption"]}</figcaption></figure>')
    first, second = html.split("</li>")[:2]
    assert "head.jpg" in first and "chart.jpg" not in first
    assert "chart.jpg" in second and "head.jpg" not in second
    assert "▲ 配圖：" + ("台灣要聞" * 10) + "…" in first


@pytest.mark.parametrize("renderer", [render_html, render_markdown, lambda d: "\n".join(render_telegram(d)), lambda d: json.dumps([p.nodes for p in render_telegraph(d)], ensure_ascii=False)])
def test_all_renderers_focus_order_clean_sections_and_cached_wording(sample_digest, renderer):
    sample_digest.focus_ids = ["sample-9", "sample-4"]
    for identifier in sample_digest.focus_ids:
        sample_digest.summaries[identifier].tier = "A"
        sample_digest.summaries[identifier].background = f"深入焦點 {identifier}"
    sample_digest.summaries["sample-2"].leader_stance = "社論主張：應持續合作。"
    rendered = renderer(sample_digest)
    assert "本週焦點" in rendered
    assert rendered.index("本週焦點") < rendered.index("深入焦點 sample-9") < rendered.index("深入焦點 sample-4")
    assert rendered.count("深入焦點 sample-9") == rendered.count("深入焦點 sample-4") == 1
    assert "社論" not in rendered and "作者主張：應持續合作。" in rendered
    assert "附錄" not in rendered and "Token：" not in rendered
    assert all(symbol not in rendered for symbol in "①②③④")
    assert "一、台灣本身" not in rendered and "二、台灣與國際" not in rendered


def test_one_sentence_card_has_no_empty_disclosure(sample_digest):
    item = entries(sample_digest)[0]
    # Entry is frozen; replace it while retaining a Taiwan association.
    item = replace(item, summary=ArticleSummary(item.article.id, "E", "一句話"))
    html = article_html(sample_digest, item)
    assert "與台灣的關聯" in html
    assert "閱讀摘要" not in html and "<details" not in html


def test_telegraph_only_leading_cover_and_navigation_after_it(sample_digest):
    sample_digest.focus_ids = ["sample-4"]
    pages = render_telegraph(sample_digest, 10000, cover_url="https://site.example/covers/example.jpg")
    assert [page.key.split(":")[0] for page in pages] == ["weekly", "focus", "international", "topics", "english"]
    for page in with_navigation(pages, {p.key: "https://telegra.ph/" + p.key for p in pages}):
        assert page.nodes[0]["tag"] == "figure"
        assert page.nodes[0]["children"][0] == {"tag": "img", "attrs": {"src": "https://site.example/covers/example.jpg"}, "children": []}
        assert "本期封面：" in json.dumps(page.nodes[0], ensure_ascii=False)
        assert page.nodes[1]["tag"] == "p"
        def inspect(nodes):
            for node in nodes:
                if isinstance(node, dict):
                    assert node["tag"] not in ("img", "figure", "video", "iframe")
                    inspect(node.get("children", []))
        inspect(page.nodes[1:])
        assert len(json.dumps(page.nodes, ensure_ascii=False, separators=(",", ":")).encode()) <= 10000


def test_publish_rsync_scope_permissions_cover_reuse_and_failure(sample_digest, tmp_path, monkeypatch):
    site = build_site(sample_digest, tmp_path / "output", images=IssueImages(cover=blobs()[0]))
    record = tmp_path / "data/site_publish.json"
    config = SiteConfig(True, "https://site.example", "example-host", "/srv/example", 17)
    calls = []
    monkeypatch.setattr("econ_digest.site.publish.subprocess.run", lambda args, **kw: calls.append((args, kw)))
    result = publish_site(site, config, record)
    assert result.index_url == "https://site.example/2026-10-03/index.html"
    name = json.loads(record.read_text())["cover_name"]
    assert result.cover_url == "https://site.example/covers/" + name
    assert calls[0][0][:6] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=17", "example-host"]
    for args, kw in calls[1:]:
        assert args[0] == "rsync" and "-a" in args and "--chmod=D755,F644" in args
        assert kw["stdin"] == subprocess.DEVNULL and kw["timeout"] == 17
        if "--delete" in args:
            assert args[-1] in ("example-host:/srv/example/2026-10-03/", "example-host:/srv/example/assets/")
    assert calls[1][0][-2] == str(site.directory) + "/"
    assert calls[-1][0][-1].endswith("/covers/" + name)
    publish_site(site, config, record)
    assert json.loads(record.read_text())["cover_name"] == name
    before = record.read_bytes()
    publish_site(site, config, record, dry_run=True, log=lambda _: None)
    assert record.read_bytes() == before and len(calls) == 10
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("ssh", 17)
    monkeypatch.setattr("econ_digest.site.publish.subprocess.run", fail)
    assert publish_site(site, config, record, log=lambda _: None) is None


def test_nested_backup_first_push_no_change_second_issue_and_failure(tmp_path, caplog):
    remote = tmp_path / "private-remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    output = tmp_path / "output"
    output.mkdir()
    (output / "2026-10-03.html").write_text("synthetic first issue")
    config = BackupConfig(True, str(remote), "main", "Example Backup", "backup@example.invalid")
    assert backup_output(output, config, "2026.10.03", tmp_path / "data")
    def head():
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=output, check=True, capture_output=True, text=True).stdout
    first = head()
    assert backup_output(output, config, "2026.10.03", tmp_path / "data") and head() == first
    (output / "2026-10-10.html").write_text("synthetic second issue")
    assert backup_output(output, config, "2026.10.10", tmp_path / "data") and head() != first
    state = load_state(tmp_path / "data")
    assert state["backup"]["issue_date"] == "2026-10-10" and "pushed_at" in state["backup"]
    broken = replace(config, remote=str(tmp_path / "nonexistent.git"))
    assert not backup_output(output, broken, "2026.10.10", tmp_path / "data", log=lambda _: None)
    assert "備份失敗" in caplog.text and "error" in load_state(tmp_path / "data")["backup"]


def test_backup_dry_run_never_creates_nested_repo_or_state(tmp_path, monkeypatch):
    monkeypatch.setattr("econ_digest.site.backup.subprocess.run", lambda *a, **kw: pytest.fail("dry run must not invoke git"))
    logs = []
    assert not backup_output(tmp_path / "output", BackupConfig(True, "https://example.invalid/private.git"), "2026.10.03", tmp_path / "data", dry_run=True, log=logs.append)
    assert logs and not (tmp_path / "output").exists() and not (tmp_path / "data").exists()


def test_backup_commands_are_local_noninteractive_and_never_force(tmp_path, monkeypatch):
    root = tmp_path / "output"
    commands = []
    def run(args, **kwargs):
        commands.append((args, kwargs))
        if args[1:2] == ["init"]:
            (root / ".git").mkdir()
        stdout = "index.html\n" if args[1:3] == ["diff", "--cached"] else ""
        return subprocess.CompletedProcess(args, 0, stdout, "")
    monkeypatch.setenv("GIT_DIR", "/example/code-repo/.git")
    monkeypatch.setattr("econ_digest.site.backup.subprocess.run", run)
    config = BackupConfig(True, "https://example.invalid/private.git", "main", "Example", "backup@example.invalid")
    assert backup_output(root, config, "2026.10.03", tmp_path / "data")
    assert commands[0][0] == ["git", "init", "-b", "main"]
    assert ["git", "remote", "add", "origin", config.remote] in [args for args, _ in commands]
    assert ["git", "commit", "-m", "備份 2026-10-03 號"] in [args for args, _ in commands]
    assert commands[-1][0] == ["git", "push", "--set-upstream", "origin", "main"]
    for args, options in commands:
        assert options["cwd"] == root and options["stdin"] == subprocess.DEVNULL
        assert options["timeout"] == 60 and options["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert "GIT_DIR" not in options["env"] and "--force" not in args


def test_backup_rejects_code_repository_without_git_calls(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='example'\n")
    monkeypatch.setattr("econ_digest.site.backup.subprocess.run", lambda *a, **kw: pytest.fail("must never touch the code repository"))
    assert not backup_output(tmp_path, BackupConfig(True, "https://example.invalid/private.git"), "2026.10.03", tmp_path / "data", log=lambda _: None)
    assert not (tmp_path / ".git").exists()
