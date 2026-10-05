"""Best-effort backup of the nested output repository, never the code checkout."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess

from ..config import BackupConfig
from ..state import load_state, save_state, utc_now

logger = logging.getLogger(__name__)


def backup_output(output_dir: str | Path, config: BackupConfig, issue_date: str,
                  data_dir: str | Path, *, dry_run: bool = False, record_state: bool = True,
                  timeout: int = 60, log=print) -> bool:
    if not config.enabled:
        return False
    date = issue_date.replace(".", "-")
    if dry_run:
        log(f"將備份 {date} 號網站與 epub 至私人儲存庫。")
        return False
    root = Path(output_dir).resolve()
    result = {"issue_date": date}
    try:
        if root == Path(__file__).resolve().parents[3] or (root / "pyproject.toml").exists():
            raise ValueError("備份目錄不可指向程式碼儲存庫")
        root.mkdir(parents=True, exist_ok=True)
        env = {key: value for key, value in os.environ.items() if key not in {
            "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"}}
        env["GIT_TERMINAL_PROMPT"] = "0"
        def git(*args):
            return subprocess.run(["git", *args], cwd=root, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, check=True, timeout=timeout, env=env)
        first = not (root / ".git").exists()
        if first:
            git("init", "-b", config.branch)
        # Refuse a .git indirection: the output folder must own its repository.
        if not (root / ".git").is_dir() or (root / ".git").is_symlink():
            raise ValueError("備份目錄不是獨立儲存庫")
        remotes = git("remote").stdout.splitlines()
        if "origin" not in remotes:
            git("remote", "add", "origin", config.remote)
        elif git("remote", "get-url", "origin").stdout.strip() != config.remote:
            git("remote", "set-url", "origin", config.remote)
        if config.author_name:
            git("config", "user.name", config.author_name)
        if config.author_email:
            git("config", "user.email", config.author_email)
        git("add", "-A")
        changed = bool(git("diff", "--cached", "--name-only").stdout.strip())
        if changed:
            git("commit", "-m", f"備份 {date} 號")
        # Also retries an unpushed commit after a previous network failure.
        git("push", "--set-upstream", "origin", config.branch)
        result["pushed_at"] = utc_now()
        ok = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result["error"] = type(error).__name__
        logger.warning("網站備份失敗（%s）；導讀傳送繼續。", type(error).__name__)
        log(f"網站備份失敗（{type(error).__name__}）；導讀傳送繼續。")
        ok = False
    if record_state:
        state = load_state(data_dir)
        state["backup"] = result
        save_state(data_dir, state)
    return ok
