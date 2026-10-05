"""Upload only issue-scoped directories and shared assets over noninteractive SSH."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import tempfile
import time

from ..config import SiteConfig
from ..models import save_json
from ..state import utc_now
from .build import BuiltSite

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedSite:
    index_url: str
    cover_url: str | None


class PublishError(RuntimeError):
    """A transport failure; publish_site logs it and preserves report fallback."""


def _stderr_tail(stream) -> str:
    stream.seek(0, 2)
    stream.seek(max(0, stream.tell() - 8192))
    detail = stream.read().decode("utf-8", errors="replace")
    detail = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", detail)
    detail = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", detail)
    detail = re.sub(r"(?i)(https?://)[^/\s@]+@", r"\1[redacted]@", detail)
    detail = re.sub(
        r"(?i)(\b(?:[\w-]*token|password|passwd|secret|api[_-]?key|authorization)\b\s*[:=]\s*)"
        r"(?:bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s&]+)",
        r"\1[redacted]", detail,
    )
    detail = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [redacted]", detail)
    return "\n".join(detail.strip().splitlines()[-5:])[-2048:]


def _run_ssh(ssh: list[str], script: str, timeout: int, operation: str,
             *, stdin=subprocess.DEVNULL, data: bytes | None = None) -> None:
    # Do not stringify subprocess exceptions: they contain the full SSH command.
    with tempfile.TemporaryFile() as errors:
        try:
            options = {"stdin": stdin} if data is None else {"input": data}
            result = subprocess.run([*ssh, script], stdout=subprocess.DEVNULL,
                                    stderr=errors, timeout=timeout, **options)
        except subprocess.TimeoutExpired:
            message = f"{operation}: timed out after {timeout} seconds"
        except OSError as error:
            message = f"{operation}: could not start ssh ({error.strerror})"
        else:
            if result.returncode == 0:
                return
            message = f"{operation}: ssh exited with status {result.returncode}"
        detail = _stderr_tail(errors)
        raise PublishError(message + (f"; stderr tail:\n{detail}" if detail else ""))


def _preflight(ssh: list[str], timeout: int) -> None:
    for executable in ("ssh", "tar"):
        if shutil.which(executable) is None:
            raise PublishError(f"Local {executable} executable not found on PATH; publishing requires ssh and tar")
    _run_ssh(ssh, "command -v tar", timeout, "Remote tar preflight (tar is required)")


def _directory_script(remote: str, name: str) -> str:
    nonce = secrets.token_hex(16)
    incoming = f"{remote}/.incoming"
    staging = f"{incoming}/{name}.{nonce}"
    backup = f"{staging}.backup"
    target = f"{remote}/{name}"
    # All failure-prone extraction and permission work happens before moving the
    # old tree. The EXIT trap restores it if installing the staged tree fails.
    return f"""set -eu
incoming={shlex.quote(incoming)}
staging={shlex.quote(staging)}
backup={shlex.quote(backup)}
target={shlex.quote(target)}
had_old=0
installed=0
committed=0
created=0
cleanup() {{
    status=$?
    trap - EXIT HUP INT TERM
    if [ "$committed" -eq 0 ]; then
        if [ "$installed" -eq 1 ]; then rm -rf -- "$target"; fi
        if [ "$had_old" -eq 1 ]; then
            mv -T -- "$backup" "$target" || {{
                echo 'Could not restore previous directory; backup retained in .incoming' >&2
                exit 1
            }}
        fi
    fi
    if [ "$created" -eq 1 ]; then rm -rf -- "$staging" || :; fi
    exit "$status"
}}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
[ ! -L "$incoming" ] || {{ echo '.incoming must not be a symlink' >&2; exit 1; }}
mkdir -p -- "$incoming"
chmod 755 -- "$incoming"
[ ! -e "$backup" ] && [ ! -L "$backup" ]
mkdir -- "$staging"
created=1
tar -xf - -C "$staging" --no-same-owner
find "$staging" -type d -exec chmod 755 {{}} +
find "$staging" -type f -exec chmod 644 {{}} +
if [ -e "$target" ] || [ -L "$target" ]; then
    mv -T -- "$target" "$backup"
    had_old=1
fi
mv -T -- "$staging" "$target"
installed=1
committed=1
# A cleanup failure must not turn a successful swap into a failed publication:
# deleting a backup is irreversible, so it cannot participate in rollback.
if [ "$had_old" -eq 1 ]; then
    rm -rf -- "$backup" || echo 'Published directory; backup cleanup failed in .incoming' >&2
fi
"""


def _upload_directory(directory: Path, remote: str, name: str,
                      ssh: list[str], timeout: int) -> None:
    script = _directory_script(remote, name)
    started = time.monotonic()
    with tempfile.TemporaryFile() as errors:
        try:
            producer = subprocess.Popen(["tar", "-C", str(directory), "-cf", "-", "."],
                                        stdout=subprocess.PIPE, stderr=errors)
        except OSError as error:
            raise PublishError(f"Upload {name}: could not start tar ({error.strerror})") from None
        try:
            try:
                try:
                    _run_ssh(ssh, script, timeout, f"Upload {name}", stdin=producer.stdout)
                except PublishError as error:
                    if producer.poll() is None:
                        producer.kill()
                    producer.wait()
                    detail = _stderr_tail(errors)
                    if detail:
                        raise PublishError(f"{error}; local tar stderr tail:\n{detail}") from None
                    raise
            finally:
                producer.stdout.close()
            try:
                producer.wait(timeout=max(0.1, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                raise PublishError(f"Upload {name}: local tar timed out after {timeout} seconds") from None
            if producer.returncode:
                detail = _stderr_tail(errors)
                raise PublishError(f"Upload {name}: local tar exited with status {producer.returncode}"
                                   + (f"; stderr tail:\n{detail}" if detail else ""))
        finally:
            if producer.poll() is None:
                producer.kill()
            producer.wait()


def _file_script(remote: str, name: str) -> str:
    target = f"{remote}/{name}"
    parent = target.rsplit("/", 1)[0]
    temporary = target + ".tmp" if name.startswith("covers/") else target + ".tmp." + secrets.token_hex(16)
    return f"""set -eu
parent={shlex.quote(parent)}
target={shlex.quote(target)}
temporary={shlex.quote(temporary)}
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
mkdir -p -- "$parent"
chmod 755 -- "$parent"
cat > "$temporary"
chmod 644 -- "$temporary"
mv -T -- "$temporary" "$target"
trap - EXIT HUP INT TERM
"""


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
        remote = config.remote_dir.rstrip("/")
        if (not remote.startswith("/") or ".." in remote.split("/")
                or not any(part not in ("", ".") for part in remote.split("/"))):
            raise PublishError("site.remote_dir must be an absolute path other than /, without '..'")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", site.issue_date):
            raise PublishError("Site issue_date must use YYYY-MM-DD")
        import json
        previous = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else {}
        cover_name = previous.get("cover_name")
        if not isinstance(cover_name, str) or not re.fullmatch(r"[a-f0-9]{32}\.jpg", cover_name):
            cover_name = secrets.token_hex(16) + ".jpg"
        # Persist identity before networking so retries use the same public name.
        save_json(record_path, {"cover_name": cover_name, "index_url": index_url,
                                "cover_url": f"{base}/covers/{cover_name}" if site.cover else None})
        ssh = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={config.ssh_timeout_seconds}", config.ssh_host]
        timeout = config.ssh_timeout_seconds
        _preflight(ssh, timeout)
        _upload_directory(site.directory, remote, site.issue_date, ssh, timeout)
        with (site.root / "index.html").open("rb") as index:
            _run_ssh(ssh, _file_script(remote, "index.html"), timeout, "Upload index.html", stdin=index)
        _upload_directory(site.root / "assets", remote, "assets", ssh, timeout)
        cover_url = None
        if site.cover:
            _run_ssh(ssh, _file_script(remote, f"covers/{cover_name}"), timeout,
                     "Upload cover", data=site.cover.data)
            cover_url = f"{base}/covers/{cover_name}"
        save_json(record_path, {"cover_name": cover_name, "index_url": index_url, "cover_url": cover_url, "published_at": utc_now()})
        return PublishedSite(index_url, cover_url)
    except (PublishError, OSError, ValueError, subprocess.SubprocessError) as error:
        detail = str(error) if isinstance(error, PublishError) else type(error).__name__
        message = f"私人網站發布失敗；改用單檔 HTML 報告。 {detail}"
        logger.warning("%s", message)
        log(message)
        return None
