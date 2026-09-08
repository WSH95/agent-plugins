# Cross-platform support (Ubuntu / Windows / macOS)

## Design

- Core behavior lives in Python (3.7+, standard library only): pathlib
  paths, subprocess git calls, json/difflib/string.Template. No canonical
  hook depends on Bash; the v0.1 shell scripts are gone.
- Atomic writes use tempfile + os.replace (safe on NTFS). Generated text uses
  UTF-8 and LF (`"\n"`) newlines for deterministic diffs on all OSes. Raw
  migration backup files retain the original bytes, including CRLF newlines.
- Paths with spaces, Unicode, drive letters, and nested repos use pathlib,
  os.path, and argument-list subprocess calls (no shell string interpolation).
  Commit paths keep their lexical final component so symlinks remain symlinks;
  resolved parent checks reject repository escapes. Git supplies operation
  metadata paths for ordinary repositories, worktrees, and `.git` files.

## Supported Python versions and CI

- Ubuntu supports Python 3.7 and later. Windows and macOS require Python 3.10
  or later. The package metadata and shared core keep a Python 3.7 floor.
- CI requests exactly 11 combinations:
  - `ubuntu-latest`: Python 3.8, 3.10, 3.12, and 3.13.
  - `ubuntu-22.04`: Python 3.7.
  - `windows-latest`: Python 3.10, 3.12, and 3.13.
  - `macos-latest`: Python 3.10, 3.12, and 3.13.

## Python 3.7 compatibility choices

- `tomllib` (3.11+) is used when present; otherwise `tomlmini` parses the
  documented flat-TOML subset of config.toml (sections, strings, ints,
  floats, booleans, comments; no arrays/dates/multiline).
- No walrus operator, no builtin-generic annotations at runtime
  (`from __future__ import annotations`), no `shutil.copytree(...,
  dirs_exist_ok=...)`, no `str.removeprefix`.
- Python 3.7 is end-of-life upstream; Ubuntu support remains because lab
  machines, clusters, and embedded robots (e.g. Jetson images) still run it.
  CI pins the 3.7 job to `ubuntu-22.04`.

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
