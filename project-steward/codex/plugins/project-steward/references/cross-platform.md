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

`project-steward hook <event> --agent <x>` is the canonical hook command.
The generated Claude Code payload includes a pure-Python
`bin/project-steward` launcher that prepends the plugin-local `src/`
directory and calls the same CLI entrypoint. Claude Code's hook schema
has no per-OS command field (ADR 0019), so every Claude hook invokes one
polyglot wrapper, `hooks/run-hook.cmd` — simultaneously a valid POSIX
shell script and a valid cmd.exe batch file. Claude Code runs hook
commands through bash where available (Linux, macOS, Git Bash on
Windows) and through PowerShell on Windows without Git Bash; both routes
reach the same wrapper. The wrapper tries `python3`/`python`/`py`
(POSIX) or `py -3`/`python` (Windows) against the bundled launcher,
falls back to a `project-steward` console script on PATH, and exits 0
silently when neither exists. No hook installs dependencies, downloads a
runtime, or relies on native binaries. Codex hooks still use the console
script because Codex does not install the Claude payload; if Codex hooks
are unavailable, disabled, or untrusted in a client, the AGENTS.md
protocol + skills/prompts + manual CLI carry the behavior there.

## Known Windows notes

- Claude Code executes hook commands via Git Bash when installed, else
  PowerShell; `run-hook.cmd` behaves the same under both (Git Bash runs
  it as a shell script; PowerShell hands `.cmd` files to cmd.exe). Git
  Bash is NOT required.
- The wrapper needs the Python Launcher (`py -3`) or `python` on PATH to
  use the bundled runtime; otherwise it falls back to an installed
  `project-steward` console script, or does nothing.
- `git` must be on PATH (Git for Windows is fine).
- PowerShell examples: `pipx install .` (from a checkout — not yet on
  PyPI); `project-steward resume`; paths may use either separator.
