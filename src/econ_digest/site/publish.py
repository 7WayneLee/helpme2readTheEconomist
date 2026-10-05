"""Upload only issue-scoped directories and shared assets over noninteractive SSH."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import tempfile

from ..config import SiteConfig
from ..models import save_json
from ..state import utc_now
from .build import BuiltSite

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedSite:
    index_url: str
    cover_url: str | None


def publish_site(site: BuiltSite, config: SiteConfig, record_path: Path, *, dry_run: bool = False,
                 log=print) -> PublishedSite | None:
    if not config.enabled:
        return None
    base = config.base_url.rstrip("/")
    index_url = f"{base}/{site.issue_date}/index.html"
    if dry_run:
        log(f"將發布私人網站：{index_url}（含 epub、圖片與共用樣式）")
        return None
    try:
        import json
        previous = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else {}
        cover_name = previous.get("cover_name")
        if not isinstance(cover_name, str) or not re.fullmatch(r"[a-f0-9]{32}\.jpg", cover_name):
            cover_name = secrets.token_hex(16) + ".jpg"
        # Persist identity before networking so retries use the same public name.
        save_json(record_path, {"cover_name": cover_name, "index_url": index_url,
                                "cover_url": f"{base}/covers/{cover_name}" if site.cover else None})
        remote = config.remote_dir.rstrip("/")
        ssh = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={config.ssh_timeout_seconds}"]
        timeout = config.ssh_timeout_seconds
        def run(args):
            subprocess.run(args, check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        run([*ssh, config.ssh_host, "mkdir -p -- " + " ".join(shlex.quote(path) for path in (f"{remote}/{site.issue_date}", f"{remote}/assets", f"{remote}/covers"))])
        rsync = ["rsync", "-a", "--chmod=D755,F644", "-e", shlex.join(ssh)]
        run([*rsync, "--delete", str(site.directory) + "/", f"{config.ssh_host}:{remote}/{site.issue_date}/"])
        run([*rsync, str(site.root / "index.html"), f"{config.ssh_host}:{remote}/index.html"])
        run([*rsync, "--delete", str(site.root / "assets") + "/", f"{config.ssh_host}:{remote}/assets/"])
        cover_url = None
        if site.cover:
            with tempfile.TemporaryDirectory(prefix="econ-cover-") as temporary:
                cover = Path(temporary) / cover_name
                cover.write_bytes(site.cover.data)
                run([*rsync, str(cover), f"{config.ssh_host}:{remote}/covers/{cover_name}"])
            cover_url = f"{base}/covers/{cover_name}"
        save_json(record_path, {"cover_name": cover_name, "index_url": index_url, "cover_url": cover_url, "published_at": utc_now()})
        return PublishedSite(index_url, cover_url)
    except (OSError, ValueError, subprocess.SubprocessError):
        logger.warning("私人網站發布失敗；改用單檔 HTML 報告。")
        log("私人網站發布失敗；改用單檔 HTML 報告。")
        return None
