#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mode=install
config_path=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --print-units) mode=print; unit_dir="${2:?需要輸出目錄}"; shift 2 ;;
        --config) config_path="${2:?需要設定檔路徑}"; shift 2 ;;
        --uninstall) mode=uninstall; shift ;;
        *) printf '%s\n' '用法：deploy/install-threads-timer.sh [--config PATH] [--print-units DIR | --uninstall]' >&2; exit 2 ;;
    esac
done
if [[ $mode == uninstall ]]; then
    systemctl --user disable --now econ-digest-threads.timer
    rm -f -- "$unit_dir/econ-digest-threads.service" "$unit_dir/econ-digest-threads.timer"
    systemctl --user daemon-reload
    printf '%s\n' '已移除 Threads 使用者定時器。'
    exit 0
fi
cd -- "$repo_dir"
"$repo_dir/.venv/bin/python" - "$repo_dir" "$unit_dir" "$config_path" <<'PY'
from pathlib import Path
import sys
from econ_digest.config import load_config
repo, target, selected = sys.argv[1:]
config = load_config(selected or None)

def quoted(value):
    return value.replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"').replace('$', '$$')

args = '--config "' + quoted(str(Path(selected).expanduser().resolve())) + '" ' if selected else ''
values = {'@REPO@': repo.replace('%', '%%'), '@EXEC_REPO@': quoted(repo),
          '@CONFIG_ARGS@': args, '@INTERVAL@': str(config.social.threads.interval_minutes)}
destination = Path(target)
destination.mkdir(parents=True, exist_ok=True)
for name in ('econ-digest-threads.service', 'econ-digest-threads.timer'):
    text = (Path(repo) / 'deploy/systemd' / (name + '.in')).read_text()
    for key, value in values.items():
        text = text.replace(key, value)
    path = destination / name
    path.write_text(text)
    path.chmod(0o644)
PY
if [[ $mode == print ]]; then
    exit 0
fi
systemctl --user daemon-reload
systemctl --user enable --now econ-digest-threads.timer
systemctl --user list-timers econ-digest-threads.timer
printf '%s\n' 'Threads 定時器已安裝；設定 enabled = true 且有有效權杖才會發布。'
