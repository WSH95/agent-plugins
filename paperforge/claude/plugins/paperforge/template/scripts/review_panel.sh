#!/usr/bin/env bash
# Portable entry point for isolated manuscript snapshots and resumable panels.
# BACKEND=claude|codex|grok scripts/review_panel.sh N [--resume]
#   [--reviewers reviewer-stats,reviewer-theory] [--jobs N]
# BRIEFING=1 explicitly adds the source-verified briefing pack.
# See --help. The Python runner uses only the standard library (3.8+).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${HERE}/review_panel.py" "$@"
