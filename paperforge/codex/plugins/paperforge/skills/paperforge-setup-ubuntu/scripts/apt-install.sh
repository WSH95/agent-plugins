#!/usr/bin/env bash
# Internal package stage; invoked through privileged.sh, never runs Code itself.
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
    echo 'This package stage requires sudo.' >&2
    exit 1
fi
# /etc/os-release is supplied by the operating system, not the workspace.
# shellcheck disable=SC1091
source /etc/os-release
if [[ ${ID:-} != ubuntu ]]; then
    echo 'Package installation supports Ubuntu only.' >&2
    exit 1
fi
install_code=false
if [[ ${1:-} == --vscode ]]; then
    install_code=true
    shift
fi
for package in "$@"; do
    case $package in
        latexmk|texlive-latex-extra|texlive-fonts-recommended|texlive-science|texlive-xetex|biber|poppler-utils|python3) ;;
        *) echo "Unsupported setup package: $package" >&2; exit 2 ;;
    esac
done
apt-get update
if [[ $# -gt 0 ]]; then
    apt-get install --no-remove -y "$@"
fi
if $install_code; then
    architecture=$(dpkg --print-architecture)
    case $architecture in
        amd64|arm64|armhf) ;;
        *) echo "VS Code apt package unavailable for $architecture" >&2; exit 1 ;;
    esac
    apt-get install --no-remove -y ca-certificates curl gpg
    key=/usr/share/keyrings/paperforge-microsoft.gpg
    source_file=/etc/apt/sources.list.d/paperforge-vscode.sources
    # Reuse only sources apt actually enables; .save files and Enabled: no do not count.
    script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
    repo_status=0
    python3 "$script_dir/vscode_repository.py" || repo_status=$?
    if [[ $repo_status -gt 1 ]]; then
        exit "$repo_status"
    fi
    if [[ $repo_status -eq 1 ]]; then
        if [[ -e $key || -L $key || -e $source_file || -L $source_file ]]; then
            echo 'Paperforge VS Code repository files already exist but do not match; inspect them before retrying.' >&2
            exit 1
        fi
        scratch=$(mktemp -d)
        trap 'rm -rf -- "$scratch"' EXIT
        curl --fail --location --proto '=https' --tlsv1.2 https://packages.microsoft.com/keys/microsoft.asc -o "$scratch/microsoft.asc"
        gpg --batch --dearmor --output "$scratch/microsoft.gpg" "$scratch/microsoft.asc"
        install -m 0644 "$scratch/microsoft.gpg" "$key"
        cat > "$source_file" <<EOF
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Architectures: $architecture
Signed-By: $key
EOF
    fi
    apt-get update
    apt-get install --no-remove -y code
fi
