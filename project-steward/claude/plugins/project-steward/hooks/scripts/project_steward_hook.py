#!/usr/bin/env python3
"""Zero-install hook shim (POSIX fallback).

Bootstraps the bundled package from the plugin checkout so hooks work even
when `project-steward` is not pip-installed:

    python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/project_steward_hook.py" \
        session-start --agent claude

Prefer the installed console script (`project-steward hook ...`) — it is
the only variant that also works on Windows shells.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

try:
    from project_steward.hooks import main
except Exception:  # never break the agent loop
    sys.exit(0)

if __name__ == "__main__":
    sys.exit(main())
