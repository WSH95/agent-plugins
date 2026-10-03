#!/usr/bin/env bash
# Authenticate on the user's terminal, never through a password pipe or log.
set -euo pipefail

terminal_child=false
if [[ ${1:-} == --terminal ]]; then
    terminal_child=true
    shift
fi
if [[ $# -lt 2 ]]; then
    echo 'Usage: bash privileged.sh LOG COMMAND [ARGS...]' >&2
    exit 2
fi
log=$1
shift
if $terminal_child; then
    # This branch only runs in the user's terminal. sudo's prompt is not logged.
    trap 'rc=$?; printf "%s\n" "$rc" > "$log.exit"' EXIT
    sudo -v
    sudo -n -- "$@" 2>&1 | tee -a "$log"
    exit 0
fi
# The caller supplies a fresh per-run log, never an existing arbitrary file.
(set -o noclobber; : > "$log")
if sudo -n true 2>/dev/null; then
    # The log belongs to the desktop user; sudo must not own the redirection.
    # shellcheck disable=SC2024
    sudo -n -- "$@" >> "$log" 2>&1
elif [[ -t 0 && -t 1 ]]; then
    bash "${BASH_SOURCE[0]}" --terminal "$log" "$@"
elif [[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]]; then
    self=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/privileged.sh
    if command -v gnome-terminal >/dev/null 2>&1; then
        gnome-terminal --wait --title='Paperforge Ubuntu setup — sudo' -- bash "$self" --terminal "$log" "$@" &
    elif command -v x-terminal-emulator >/dev/null 2>&1; then
        x-terminal-emulator -e bash "$self" --terminal "$log" "$@" &
    else
        echo 'No supported desktop terminal. Run the setup command in your own terminal.' >&2
        exit 3
    fi
    terminal_pid=$!
    # Some terminal launchers detach; the completion marker is authoritative.
    for ((attempt=0; attempt<3600; attempt++)); do
        if [[ -f $log.exit ]]; then
            rc=$(cat -- "$log.exit")
            wait "$terminal_pid" || true
            [[ $rc =~ ^[0-9]+$ ]] || exit 1
            exit "$rc"
        fi
        if ! kill -0 "$terminal_pid" 2>/dev/null; then
            launch_rc=0
            wait "$terminal_pid" || launch_rc=$?
            if [[ $launch_rc -ne 0 ]]; then
                echo 'Could not open the authentication terminal; run setup in your own terminal.' >&2
                exit "$launch_rc"
            fi
        fi
        sleep 1
    done
    echo "Terminal authentication/install did not finish within one hour. See $log" >&2
    exit 3
else
    echo 'Sudo authentication needs your terminal. Run the setup command there; do not send a password to the agent.' >&2
    exit 3
fi
