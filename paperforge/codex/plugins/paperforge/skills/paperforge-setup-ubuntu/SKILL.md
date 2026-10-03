---
name: paperforge-setup-ubuntu
description: Set up and verify the local Ubuntu LaTeX writing environment only when the user explicitly invokes paperforge-setup-ubuntu. Supports checking an existing host, installing missing TeX tools and VS Code, preserving editor settings, and testing PDF preview.
disable-model-invocation: true
---

# Ubuntu LaTeX Setup

Run only on explicit user invocation. A bare invocation requests installation,
configuration, and verification. If the user requests inspection only, use
`check` and report the findings. Ordinary writing, new-paper, adoption, and plugin
installation do not invoke this workflow.

## Run the bundled helpers

Resolve this skill directory from the loaded `SKILL.md` location. Its scripts
and assets are self-contained; do not require the source checkout or a paper
workspace. Invoke scripts through `bash`, because plugin packaging may remove
executable bits.

1. Run `bash "<skill-dir>/scripts/setup-ubuntu.sh" check`. Inspect OS, existing
   tools, conflicts, and settings. Ubuntu desktop is the target. On other OSes,
   stop. On headless Ubuntu, finish available checks and report the UI limitation.
2. For setup, run `bash "<skill-dir>/scripts/setup-ubuntu.sh" install`.
   It installs missing packages, reuses or installs stable VS Code, installs
   LaTeX Workshop as the desktop user, and backs up changed JSONC preferences.
   Existing settings must parse before installation begins. Conflicting TeX
   paths require resolving which installation to use; do not remove one or
   rewrite PATH automatically.
3. If sudo needs authentication, the helper opens a desktop terminal. Tell the
   user to enter their password there. Keep the task running and inspect the
   result; never collect passwords in chat, stdin, environment variables, or
   logs. Use the harness's normal permission mechanism when needed. If no
   accessible terminal exists, give the exact helper command for their terminal
   and resume verification after it completes.
4. Run `bash "<skill-dir>/scripts/setup-ubuntu.sh" verify`. Read its report and
   logs; fix failures within this setup's scope. It builds both engines with
   Biber, checks PDF contents and SyncTeX, and tests an isolated continuous
   compiler. It restores fixture edits/settings and stops its watcher.
5. Follow [the preview protocol](references/preview.md) to test the editor and
   displayed PDF yourself using available UI/browser tools. Compiler success
   alone does not establish visible refresh. Save observed UI evidence beside
   the helper's report; mark unavailable checks `unverified`.

Helpers default to read-only `check`. `install` and `verify` create a fresh
temporary run directory and print its path. Optional `--run-dir PATH` must name
a new directory. `--settings PATH` selects an explicit JSONC settings target;
default is stable Code's default user profile under XDG config (or
`VSCODE_PORTABLE`). For named profiles/custom Code data locations, identify the
matching CLI/profile first; do not silently configure a different profile.
See [host details](references/ubuntu.md) for dependencies and recovery.

## Report

Give installed/reused versions, changed settings and backup paths, sample PDF,
and separate results for compilation, extension builds with source/PDF active,
continuous rebuilds, and visible refresh. State the working preview method and
how to start/stop it. Label skipped checks and failures accurately. Do not hand
routine compiler tests back to the user or claim preview success from settings
alone. Future writing feedback should quote the passage, name its section,
describe the intended change, and identify what must stay unchanged.
