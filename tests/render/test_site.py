from copy import deepcopy
from dataclasses import replace
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import textwrap

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
from econ_digest.site.publish import PublishError, _preflight, _run_ssh, _upload_directory, publish_site
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
        breadcrumb = html.split('<nav class="breadcrumb"', 1)[1].split('</nav>', 1)[0]
        tabs = html.split('<nav class="issue-tabs"', 1)[1].split('</nav>', 1)[0]
        assert 'href="../index.html">所有期別</a>' in breadcrumb
        assert 'class="crumb-separator" aria-hidden="true">›</span>' in breadcrumb
        if key == "index":
            assert '<span aria-current="page">2026/10/03 號</span>' in breadcrumb
            assert 'href="index.html"' not in breadcrumb and 'aria-current' not in tabs
        else:
            assert '<a href="index.html">2026/10/03 號</a>' in breadcrumb
            assert f'href="{key}.html" aria-current="page"' in tabs
            assert tabs.count('aria-current="page"') == 1
        assert "data:image" not in html
        assert 'href="../assets/site.css"' in html
        labels = ["要聞", "台灣", "焦點", "國際", "財經科技文化", "英文"]
        for other, label in zip(list(site.pages)[1:], labels):
            assert f'href="{other}.html"' in tabs and f'>{label}</a>' in tabs
        assert [tabs.index(f'>{label}</a>') for label in labels] == sorted(tabs.index(f'>{label}</a>') for label in labels)
        assert 'page-nav' not in html
        assert ('rel="prev"' in html) == (key != "index")
        assert ('rel="next"' in html) == (key not in ("index", "english"))
        if key != "index":
            position = list(site.pages).index(key)
            previous = list(site.pages)[position - 1]
            label = "本期導讀" if previous == "index" else labels[position - 2]
            assert f'<a rel="prev" href="{previous}.html">‹ {label}</a>' in html
            if key != "english":
                following = list(site.pages)[position + 1]
                assert f'<a rel="next" href="{following}.html">{labels[position]} ›</a>' in html
        assert "社論" not in html
    index = site.pages["index"].read_text()
    assert index.index('class="issue-cover"') < index.index("<h1>")
    assert "下載本期 epub" in index and '<img src="img/' in index
    assert index.count('class="section-card"') == 6
    assert '<small>3 篇</small>' in index and '<small>1 篇深度分析</small>' in index
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
    assert '<h1>所有期別</h1>' in archive and 'class="issue-tabs"' not in archive


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
    sample_digest.english.pre_reading_zh = "社論背景的合成導讀。"
    sample_digest.english.vocabulary[0].note_zh = "社論中的合成用法。"
    sample_digest.english.quiz[0].answer = "社論的合成答案。"
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
    assert [page.key.split(":")[0] for page in pages] == ["weekly", "taiwan", "focus", "international", "topics", "english"]
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


@pytest.fixture
def fake_ssh(tmp_path, monkeypatch):
    """Execute the remote shell locally, with real tar and no possible network."""
    directory = tmp_path / "fake-bin"
    directory.mkdir()
    executable = directory / "ssh"
    executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        with Path(os.environ["FAKE_SSH_CALLS"]).open("a") as calls:
            calls.write(json.dumps(args) + "\\n")
        while args[:1] == ["-o"]:
            args = args[2:]
        if len(args) != 2 or args[0] != "example-host":
            sys.exit("fake ssh accepts only the test host and one remote command")
        script = args[1]
        failure = os.environ.get("FAKE_SSH_FAILURE")
        if failure == "ssh":
            for number in range(10):
                print(f"synthetic ssh diagnostic {number}", file=sys.stderr)
            sys.exit(1)
        if failure == "missing-tar" and script == "command -v tar":
            sys.exit("synthetic remote tar unavailable")
        if failure == "timeout" and script != "command -v tar":
            script = 'echo "synthetic transport timeout" >&2; exec sleep 2'
        if failure == "extract":
            script = 'tar() { command tar "$@"; echo "synthetic extraction failure" >&2; return 1; };\\n' + script
        if failure == "permissions":
            script = 'find() { echo "synthetic chmod failure" >&2; return 1; };\\n' + script
        if failure == "install":
            script = 'mv() { case "$3" in *.backup) ;; */.incoming/*) echo "synthetic install failure" >&2; return 1;; esac; command mv "$@"; };\\n' + script
        if failure == "file-install":
            script = 'mv() { case "$3" in *.tmp*) echo "synthetic file install failure" >&2; return 1;; esac; command mv "$@"; };\\n' + script
        os.execv("/bin/sh", ["sh", "-c", script])
        '''), encoding="utf-8")
    executable.chmod(0o755)
    calls = tmp_path / "ssh-calls.jsonl"
    monkeypatch.setenv("FAKE_SSH_CALLS", str(calls))
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ["PATH"])
    return calls


def site_tree(directory):
    return {str(path.relative_to(directory)): None if path.is_dir() else path.read_bytes()
            for path in directory.rglob("*")}


def assert_site_permissions(directory):
    for path in (directory, *directory.rglob("*")):
        assert stat.S_IMODE(path.stat().st_mode) == (0o755 if path.is_dir() else 0o644), path


def test_publish_ssh_tar_end_to_end_scope_permissions_cover_reuse(sample_digest, tmp_path, illustrated_epub, fake_ssh):
    site = build_site(sample_digest, tmp_path / "local output", illustrated_epub)
    assert site.cover and (site.directory / "img").is_dir()
    # Spaces, quotes and shell syntax in the path must remain literal.
    remote = tmp_path / "remote 'quoted'; $(touch must-not-exist)"
    config = SiteConfig(True, "https://site.example", "example-host", str(remote), 17)
    record = tmp_path / "data/site_publish.json"
    old_issue = remote / "2026-09-26"
    old_issue.mkdir(parents=True)
    (old_issue / "unrelated.html").write_text("keep older issue")
    (remote / "keep.txt").write_text("keep unrelated root file")
    for path in (site.directory, *site.directory.rglob("*")):
        path.chmod(0o700 if path.is_dir() else 0o600)
    result = publish_site(site, config, record)
    assert result.index_url == "https://site.example/2026-10-03/index.html"
    name = json.loads(record.read_text())["cover_name"]
    assert result.cover_url == "https://site.example/covers/" + name
    assert site_tree(remote / site.issue_date) == site_tree(site.directory)
    assert (remote / site.issue_date / "TheEconomist.2026.10.03.epub").read_bytes() == illustrated_epub.read_bytes()
    assert (remote / "covers" / name).read_bytes() == site.cover.data
    assert (remote / "index.html").read_bytes() == (site.root / "index.html").read_bytes()
    assert site_tree(remote / "assets") == site_tree(site.root / "assets")
    assert_site_permissions(remote / site.issue_date)
    assert_site_permissions(remote / "assets")
    assert_site_permissions(remote / "covers")
    assert list((remote / ".incoming").iterdir()) == []
    calls = [json.loads(line) for line in fake_ssh.read_text().splitlines()]
    assert len(calls) == 5 and calls[0][-1] == "command -v tar"
    assert all(args[:5] == ["-o", "BatchMode=yes", "-o", "ConnectTimeout=17", "example-host"] for args in calls)
    assert "tar -xf -" in calls[1][-1] and "tar -xf -" in calls[3][-1]
    (remote / site.issue_date / "stale.html").write_text("stale page")
    (remote / "assets/stale.css").write_text("stale stylesheet")
    (site.pages["index"]).write_text("updated issue")
    (site.root / "index.html").write_text("updated archive")
    (site.root / "assets/site.css").write_text("updated css")
    updated = replace(site, cover=ImageBlob("new.jpg", "image/jpeg", b"new synthetic cover"))
    assert publish_site(updated, config, record).cover_url == result.cover_url
    assert json.loads(record.read_text())["cover_name"] == name
    assert "published_at" in json.loads(record.read_text())
    assert site_tree(remote / site.issue_date) == site_tree(site.directory)
    assert site_tree(remote / "assets") == site_tree(site.root / "assets")
    assert (remote / "index.html").read_text() == "updated archive"
    assert (remote / "covers" / name).read_bytes() == updated.cover.data
    assert list((remote / "covers").iterdir()) == [remote / "covers" / name]
    assert (old_issue / "unrelated.html").read_text() == "keep older issue"
    assert (remote / "keep.txt").read_text() == "keep unrelated root file"
    assert list((remote / ".incoming").iterdir()) == []
    assert not Path("must-not-exist").exists()
    assert_site_permissions(remote / site.issue_date)
    assert_site_permissions(remote / "assets")


@pytest.mark.parametrize("failure,diagnostic", [("ssh", "synthetic ssh diagnostic 9"),
                                              ("missing-tar", "synthetic remote tar unavailable"),
                                              ("extract", "synthetic extraction failure"),
                                              ("permissions", "synthetic chmod failure"),
                                              ("install", "synthetic install failure"),
                                              ("timeout", "synthetic transport timeout")])
def test_publish_remote_failure_keeps_previous_tree_and_logs_stderr(sample_digest, tmp_path, monkeypatch, caplog,
                                                                  fake_ssh, failure, diagnostic):
    site = build_site(sample_digest, tmp_path / "output")
    remote = tmp_path / "remote"
    config = SiteConfig(True, "https://site.example", "example-host", str(remote), 1 if failure == "timeout" else 30)
    record = tmp_path / "data/site_publish.json"
    assert publish_site(site, config, record)
    before = site_tree(remote)
    (site.pages["index"]).write_text("must not replace the existing issue")
    monkeypatch.setenv("FAKE_SSH_FAILURE", failure)
    logs = []
    assert publish_site(site, config, record, log=logs.append) is None
    assert site_tree(remote) == before
    assert list((remote / ".incoming").iterdir()) == []
    assert "published_at" not in json.loads(record.read_text())
    assert diagnostic in caplog.text and diagnostic in logs[-1]
    assert "stderr tail:" in caplog.text and "改用單檔 HTML 報告" in caplog.text
    if failure == "ssh":
        assert "diagnostic 0" not in caplog.text and "diagnostic 5" in caplog.text


def test_publish_error_contains_remote_stderr_and_preserves_old_assets(tmp_path, monkeypatch, fake_ssh):
    directory = tmp_path / "local-assets"
    directory.mkdir()
    (directory / "site.css").write_text("new css")
    remote = tmp_path / "remote"
    (remote / "assets").mkdir(parents=True)
    (remote / "assets/site.css").write_text("old css")
    monkeypatch.setenv("FAKE_SSH_FAILURE", "install")
    with pytest.raises(PublishError, match="synthetic install failure"):
        _upload_directory(directory, str(remote), "assets", ["ssh", "example-host"], 10)
    assert (remote / "assets/site.css").read_text() == "old css"
    assert list((remote / ".incoming").iterdir()) == []


def test_publish_local_tar_error_keeps_previous_copy_and_includes_local_stderr(tmp_path, fake_ssh):
    remote = tmp_path / "remote"
    (remote / "assets").mkdir(parents=True)
    (remote / "assets/site.css").write_text("previous css")
    with pytest.raises(PublishError, match="local tar stderr tail:") as caught:
        _upload_directory(tmp_path / "missing-directory", str(remote), "assets", ["ssh", "example-host"], 10)
    assert "missing-directory" in str(caught.value)
    assert (remote / "assets/site.css").read_text() == "previous css"
    assert list((remote / ".incoming").iterdir()) == []


def test_publish_refuses_symlinked_staging_directory(tmp_path, fake_ssh):
    remote = tmp_path / "remote"
    remote.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep outside contents")
    (remote / ".incoming").symlink_to(outside, target_is_directory=True)
    local = tmp_path / "local"
    local.mkdir()
    with pytest.raises(PublishError, match=".incoming must not be a symlink"):
        _upload_directory(local, str(remote), "assets", ["ssh", "example-host"], 10)
    assert list(outside.iterdir()) == [outside / "keep.txt"]
    assert (outside / "keep.txt").read_text() == "keep outside contents"


@pytest.mark.parametrize("name", ["index.html", "covers/" + "a" * 32 + ".jpg"])
def test_publish_file_failure_preserves_old_file(tmp_path, monkeypatch, fake_ssh, name):
    from econ_digest.site.publish import _file_script
    remote = tmp_path / "remote"
    target = remote / name
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous content")
    monkeypatch.setenv("FAKE_SSH_FAILURE", "file-install")
    with pytest.raises(PublishError, match="synthetic file install failure"):
        _run_ssh(["ssh", "example-host"], _file_script(str(remote), name), 10, "Upload file", data=b"new content")
    assert target.read_bytes() == b"previous content"
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.parametrize("executable", ["ssh", "tar"])
def test_publish_local_preflight_error(sample_digest, tmp_path, monkeypatch, caplog, fake_ssh, executable):
    import shutil
    original = shutil.which
    monkeypatch.setattr("econ_digest.site.publish.shutil.which", lambda name: None if name == executable else original(name))
    with pytest.raises(PublishError, match=f"Local {executable} executable not found on PATH"):
        _preflight(["ssh", "example-host"], 10)
    site = build_site(sample_digest, tmp_path / "output")
    config = SiteConfig(True, "https://site.example", "example-host", str(tmp_path / "remote"))
    assert publish_site(site, config, tmp_path / "record.json", log=lambda _: None) is None
    assert f"Local {executable} executable not found on PATH" in caplog.text
    assert not fake_ssh.exists() and not (tmp_path / "remote").exists()


def test_publish_remote_preflight_error(monkeypatch, fake_ssh):
    monkeypatch.setenv("FAKE_SSH_FAILURE", "missing-tar")
    with pytest.raises(PublishError, match="Remote tar preflight.*tar is required.*stderr tail:") as caught:
        _preflight(["ssh", "example-host"], 10)
    assert "synthetic remote tar unavailable" in str(caught.value)


def test_publish_timeout_includes_stderr_and_redacts_credentials(fake_ssh):
    script = "echo 'timeout context' >&2; echo 'token=secret-value Authorization: Bearer other-secret' >&2; exec sleep 2"
    with pytest.raises(PublishError, match="timed out after 1 seconds") as caught:
        _run_ssh(["ssh", "example-host"], script, 1, "Synthetic upload")
    detail = str(caught.value)
    assert "timeout context" in detail and "[redacted]" in detail
    assert "secret-value" not in detail and "other-secret" not in detail


@pytest.mark.parametrize("remote", ["relative/path", "/", "////", "/srv/../outside", "/./"])
def test_publish_rejects_unsafe_remote_directory(sample_digest, tmp_path, caplog, fake_ssh, remote):
    site = build_site(sample_digest, tmp_path / "output")
    config = SiteConfig(True, "https://site.example", "example-host", remote)
    assert publish_site(site, config, tmp_path / "record.json", log=lambda _: None) is None
    assert "site.remote_dir must be an absolute path" in caplog.text
    assert not fake_ssh.exists()


def test_publish_rejects_issue_path_traversal(sample_digest, tmp_path, caplog, fake_ssh):
    site = replace(build_site(sample_digest, tmp_path / "output"), issue_date="../outside")
    config = SiteConfig(True, "https://site.example", "example-host", str(tmp_path / "remote"))
    assert publish_site(site, config, tmp_path / "record.json", log=lambda _: None) is None
    assert "issue_date must use YYYY-MM-DD" in caplog.text
    assert not fake_ssh.exists()


def test_publish_disabled_and_dry_run_do_not_preflight_or_change_record(sample_digest, tmp_path, monkeypatch):
    site = build_site(sample_digest, tmp_path / "output")
    record = tmp_path / "record.json"
    record.write_text('{"cover_name":"' + "a" * 32 + '.jpg"}')
    before = record.read_bytes()
    monkeypatch.setattr("econ_digest.site.publish.shutil.which", lambda _: pytest.fail("must not preflight"))
    monkeypatch.setattr("econ_digest.site.publish.subprocess.run", lambda *a, **kw: pytest.fail("must not invoke ssh"))
    assert publish_site(site, SiteConfig(), record) is None
    config = SiteConfig(True, "https://site.example", "example-host", str(tmp_path / "remote"))
    logs = []
    assert publish_site(site, config, record, dry_run=True, log=logs.append) is None
    assert record.read_bytes() == before and logs


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
