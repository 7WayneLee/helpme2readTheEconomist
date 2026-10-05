"""Report renderers and persisted delivery artifacts."""

from __future__ import annotations

from pathlib import Path

from ..models import Digest, save_json
from .html import render_html
from .markdown import render_markdown
from .telegram import render_telegram

__all__ = ["render_markdown", "render_html", "render_telegram", "write_outputs"]


def write_outputs(digest: Digest, out_dir: str | Path) -> dict[str, Path]:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {"markdown": directory / "report.md", "html": directory / "report.html",
             "telegram": directory / "telegram_messages.json"}
    paths["markdown"].write_text(render_markdown(digest), encoding="utf-8")
    paths["html"].write_text(render_html(digest), encoding="utf-8")
    save_json(paths["telegram"], render_telegram(digest))
    return paths
