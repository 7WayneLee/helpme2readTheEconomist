#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [[ ${1:-} == --uninstall && $# == 1 ]]; then
    systemctl --user disable --now econ-digest.timer
    rm -f -- "$unit_dir/econ-digest.service" "$unit_dir/econ-digest.timer"
    systemctl --user daemon-reload
    printf '%s\n' '已移除 econ-digest 使用者定時器。'
    exit 0
fi
if [[ $# != 0 ]]; then
    printf '%s\n' '用法：deploy/install-user-timer.sh [--uninstall]' >&2
    exit 2
fi

mkdir -p -- "$unit_dir"
# systemd expands percent specifiers even inside quoted paths.
escaped_repo="${repo_dir//%/%%}"
escaped_repo="${escaped_repo//\\/\\\\}"
escaped_repo="${escaped_repo//\"/\\\"}"
escaped_repo="${escaped_repo//&/\\&}"
escaped_repo="${escaped_repo//|/\\|}"
sed -e "s|WorkingDirectory=@REPO@|WorkingDirectory=\"@REPO@\"|" \
    -e 's|ExecStart=@REPO@/.venv/bin/econ-digest run|ExecStart="@REPO@/.venv/bin/econ-digest" run|' \
    -e "s|@REPO@|$escaped_repo|g" \
    "$repo_dir/deploy/systemd/econ-digest.service.in" > "$unit_dir/econ-digest.service"
install -m 644 "$repo_dir/deploy/systemd/econ-digest.timer" "$unit_dir/econ-digest.timer"
systemctl --user daemon-reload
systemctl --user enable --now econ-digest.timer
systemctl --user list-timers econ-digest.timer
printf '%s\n' '目前 lingering 未啟用；使用者定時器僅在登入期間執行。'
printf '%s\n' '若要在登出後繼續執行，可使用：loginctl enable-linger "$USER"'
