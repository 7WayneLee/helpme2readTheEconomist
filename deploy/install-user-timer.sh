#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

render_units() {
    local target_dir="$1" working_repo exec_repo line
    mkdir -p -- "$target_dir"
    working_repo="${repo_dir//%/%%}"
    exec_repo="${working_repo//\\/\\\\}"
    exec_repo="${exec_repo//\"/\\\"}"
    exec_repo="${exec_repo//\$/\$\$}"
    while IFS= read -r line || [[ -n $line ]]; do
        case "$line" in
            WorkingDirectory=*) printf 'WorkingDirectory=%s\n' "$working_repo" ;;
            ExecStart=*) printf 'ExecStart="%s/.venv/bin/econ-digest" run\n' "$exec_repo" ;;
            *) printf '%s\n' "$line" ;;
        esac
    done < "$repo_dir/deploy/systemd/econ-digest.service.in" > "$target_dir/econ-digest.service"
    install -m 644 "$repo_dir/deploy/systemd/econ-digest.timer" "$target_dir/econ-digest.timer"
}

if [[ ${1:-} == --print-units && $# == 2 && -n ${2:-} ]]; then
    render_units "$2"
    exit 0
fi
if [[ ${1:-} == --uninstall && $# == 1 ]]; then
    systemctl --user disable --now econ-digest.timer
    rm -f -- "$unit_dir/econ-digest.service" "$unit_dir/econ-digest.timer"
    systemctl --user daemon-reload
    printf '%s\n' '已移除 econ-digest 使用者定時器。'
    exit 0
fi
if [[ $# != 0 ]]; then
    printf '%s\n' '用法：deploy/install-user-timer.sh [--uninstall | --print-units DIR]' >&2
    exit 2
fi

render_units "$unit_dir"
systemctl --user daemon-reload
systemctl --user enable --now econ-digest.timer
systemctl --user list-timers econ-digest.timer
printf '%s\n' '目前 lingering 未啟用；使用者定時器僅在登入期間執行。'
printf '%s\n' '若要在登出後繼續執行，可使用：loginctl enable-linger "$USER"'
