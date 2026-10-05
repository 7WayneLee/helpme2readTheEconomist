"""Offline, filesystem-only website generation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html import escape
from importlib.resources import files
import json
from pathlib import Path
import shutil

from ..images import ImageBlob, IssueImages, load_issue_images
from ..models import Digest, save_json
from ..render.common import clean_text, english_article, overview, sections, title
from ..render.html import article_html, brief_html, english_html, paragraph


@dataclass(frozen=True)
class BuiltSite:
    issue_date: str
    root: Path
    directory: Path
    pages: dict[str, Path]
    cover: ImageBlob | None


def document(label: str, body: str, *, css: str, navigation: str = "", footer: str = "") -> str:
    template = files("econ_digest").joinpath("templates/site.html").read_text(encoding="utf-8")
    return template.replace("{{title}}", escape(label)).replace("{{css}}", css).replace("{{navigation}}", navigation).replace("{{body}}", clean_text(body)).replace("{{footer}}", footer)


def build_site(digest: Digest, output_dir: str | Path, epub: str | Path | None = None,
               *, images: IssueImages | None = None) -> BuiltSite:
    date = digest.issue_date.replace(".", "-")
    root = Path(output_dir)
    directory = root / date
    directory.mkdir(parents=True, exist_ok=True)
    assets = root / "assets"
    assets.mkdir(exist_ok=True)
    css = files("econ_digest").joinpath("templates/report.css").read_text(encoding="utf-8")
    css += files("econ_digest").joinpath("templates/site.css").read_text(encoding="utf-8")
    (assets / "site.css").write_text(css, encoding="utf-8")
    if epub is not None and Path(epub).exists():
        destination = directory / f"TheEconomist.{digest.issue_date}.epub"
        if Path(epub).resolve() != destination.resolve():
            shutil.copyfile(epub, destination)
        if images is None:
            images = load_issue_images(epub)
    images = images or IssueImages()
    used_images: set[str] = set()

    def render_image(blob: ImageBlob, alt: str, *, caption: str | None = None, cover: bool = False) -> str:
        extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/svg+xml": ".svg", "image/webp": ".webp"}.get(blob.mime, ".img")
        name = hashlib.sha256(blob.data).hexdigest()[:24] + extension
        (directory / "img").mkdir(exist_ok=True)
        (directory / "img" / name).write_bytes(blob.data)
        used_images.add(name)
        figure_class = ' class="issue-cover"' if cover else ""
        loading = "" if cover else ' loading="lazy"'
        label = f"<figcaption>{escape(caption)}</figcaption>" if caption else ""
        return f'<figure{figure_class}><img src="img/{name}" alt="{escape(alt, quote=True)}"{loading}>{label}</figure>'

    groups = sections(digest)
    contents: dict[str, tuple[str, str]] = {"index": ("本期導讀", "")}
    brief = brief_html(digest, images, render_image=render_image)
    if brief:
        contents["brief"] = ("本週要聞速覽", brief)
    for key, label, selected in (
        ("taiwan", "台灣", [s for s in groups if s.anchor.startswith("taiwan-")]),
        ("focus", "本週焦點", [s for s in groups if s.anchor == "focus"]),
        ("world", "國際", [s for s in groups if s.anchor.startswith("intl-")]),
        ("topics", "財經・科技・文化", [s for s in groups if s.anchor in ("finance", "tech", "science", "culture")]),
    ):
        if selected:
            body = ""
            for section in selected:
                if section.title != label:
                    body += f'<h2 id="{section.anchor}">{escape(section.title)}</h2>'
                body += "".join(article_html(digest, entry, images, render_image=render_image) for entry in section.entries)
            contents[key] = (label, body)
    if english_article(digest):
        contents["english"] = ("英文學習", english_html(digest))
    index = render_image(images.cover, title(digest) + " 封面", cover=True) if images.cover else ""
    index += f"<h1>{escape(title(digest))}</h1>" + paragraph(overview(digest))
    if (directory / f"TheEconomist.{digest.issue_date}.epub").exists():
        index += f'<p><a href="TheEconomist.{digest.issue_date}.epub" download>下載本期 epub</a></p>'
    index += '<div class="section-cards">' + "".join(
        f'<a class="section-card" href="{key}.html">{escape(label)}<span aria-hidden="true"> →</span></a>'
        for key, (label, _) in contents.items() if key != "index") + '</div>'
    contents["index"] = ("本期導讀", index)
    keys = list(contents)
    paths = {}
    for position, (key, (label, body)) in enumerate(contents.items()):
        navigation = '<nav class="page-nav" aria-label="分頁導覽"><a href="../index.html">所有期別</a>'
        navigation += "".join(f'<a href="{other}.html"' + (' aria-current="page"' if other == key else '') + f'>{escape(other_label)}</a>'
                              for other, (other_label, _) in contents.items()) + '</nav>'
        footer = '<footer class="page-footer">'
        if position:
            footer += f'<a href="{keys[position - 1]}.html">← 上一頁</a>'
        if position + 1 < len(keys):
            footer += f'<a href="{keys[position + 1]}.html">下一頁 →</a>'
        footer += '</footer>'
        if key != "index":
            body = f'<header><p>{escape(title(digest))}</p><h1>{escape(label)}</h1></header>' + body
        path = directory / f"{key}.html"
        path.write_text(document(title(digest) + "｜" + label, body, css="../assets/site.css", navigation=navigation, footer=footer), encoding="utf-8")
        paths[key] = path
    for key in ("brief", "taiwan", "focus", "world", "topics", "english"):
        if key not in paths:
            (directory / f"{key}.html").unlink(missing_ok=True)
    if (directory / "img").exists():
        for path in (directory / "img").iterdir():
            if path.is_file() and path.name not in used_images:
                path.unlink()
    cover_name = next((hashlib.sha256(images.cover.data).hexdigest()[:24] + suffix for suffix in (".jpg", ".png", ".gif", ".webp", ".svg", ".img")
                       if images.cover and (directory / "img" / (hashlib.sha256(images.cover.data).hexdigest()[:24] + suffix)).exists()), None)
    save_json(directory / ".issue.json", {"date": date, "title": title(digest), "overview": overview(digest), "cover": cover_name})
    archive = '<h1>經濟學人導讀封存</h1><div class="archive">'
    for metadata in sorted(root.glob("????-??-??/.issue.json"), reverse=True):
        item = json.loads(metadata.read_text(encoding="utf-8"))
        archive += f'<a class="archive-card" href="{item["date"]}/index.html">'
        if item.get("cover"):
            archive += f'<img src="{item["date"]}/img/{escape(item["cover"], quote=True)}" alt="本期封面" loading="lazy">'
        archive += '<div><h2>' + escape(item["title"]) + '</h2><p>' + escape(item["overview"]) + '</p></div></a>'
    archive += '</div>'
    (root / "index.html").write_text(document("經濟學人導讀封存", archive, css="assets/site.css"), encoding="utf-8")
    return BuiltSite(date, root, directory, paths, images.cover)
