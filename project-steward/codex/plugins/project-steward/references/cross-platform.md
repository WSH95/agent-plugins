# Cross-platform support (Ubuntu / Windows / macOS)

## Design

- Core behavior lives in Python (3.7+, standard library only): pathlib
  paths, subprocess git calls, json/difflib/string.Template. No canonical
  hook depends on Bash; the v0.1 shell scripts are gone.
- Atomic writes use tempfile + os.replace (safe on NTFS); text is written
  UTF-8 with "\n" newlines for deterministic diffs on all OSes.
- Paths with spaces, Unicode, drive letters, and nested repos are handled
  by pathlib + argument-list subprocess calls (no shell string
  interpolation).

## Python 3.7 floor — deliberate compatibility choices

- `tomllib` (3.11+) is used when present; otherwise `tomlmini` parses the
  documented flat-TOML subset of config.toml (sections, strings, ints,
  floats, booleans, comments; no arrays/dates/multiline).
- No walrus operator, no builtin-generic annotations at runtime
  (`from __future__ import annotations`), no `shutil.copytree(...,
  dirs_exist_ok=...)`, no `str.removeprefix`.
- Python 3.7 is end-of-life upstream; supported here because lab
  machines, clusters, and embedded robots (e.g. Jetson images) still run
  it. CI pins 3.7 jobs to runners that still provide it.

## Hook commands

`project-steward hook <event> --agent <x>` is the canonical hook command:
a console script on PATH works identically under sh, cmd, and PowerShell,
with no env-var expansion differences. The POSIX-only zero-install
fallback (`python3 .../hooks/scripts/project_steward_hook.py`) is emitted
in the generated Claude Code payload for un-pip-installed plugin use; on
native Windows, install the CLI (pipx/pip). If Codex hooks are
unavailable, disabled, or untrusted in a client, the AGENTS.md protocol +
skills/prompts + manual CLI carry the behavior there.

## Known Windows notes

- Claude Code hook execution on native Windows has shell quirks; the
  console-script command avoids `${VAR}` expansion entirely.
- `git` must be on PATH (Git for Windows is fine; Git Bash NOT required).
- PowerShell examples: `pipx install .` (from a checkout — not yet on
  PyPI); `project-steward resume`; paths may use either separator.
