#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    if [[ ${1:-check} != install ]]; then
        echo 'Python 3 is missing. Explicitly run install to bootstrap it on Ubuntu.' >&2
        exit 1
    fi
    # Bootstrapping still checks Ubuntu in apt-install.sh before any apt action.
    run_dir=$(mktemp -d -t paperforge-python-XXXXXX)
    echo "Python bootstrap log: $run_dir/packages.log"
    bash "$script_dir/privileged.sh" "$run_dir/packages.log" bash "$script_dir/apt-install.sh" python3
fi
exec python3 "$script_dir/setup_ubuntu.py" "$@"
