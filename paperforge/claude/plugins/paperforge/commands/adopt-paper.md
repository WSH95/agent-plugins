---
description: Add Paperforge scaffolding to an existing (or empty, prepared) directory in place — no-clobber; --force keeps timestamped backups; --refresh updates single scaffolding files.
argument-hint: "[--force|--steward] [--refresh <path>] [/path/to/existing-paper | .]"
---

Adopt a directory in place as a Paperforge paper workspace
($ARGUMENTS; with no argument, propose the current directory and confirm
before writing).

1. Run the bundled script (the single source of scaffolding logic):

   bash "${CLAUDE_PLUGIN_ROOT}/adopt-paper.sh" [--force] "<directory>"

   If the ${CLAUDE_PLUGIN_ROOT} placeholder was not expanded in this text,
   resolve the newest ~/.claude/plugins/cache/*/paperforge/*/ directory
   (any marketplace name) and run its adopt-paper.sh. Never re-implement
   the copy logic yourself. `--force` overwrites scaffolding files with
   timestamped .bak backups — warn the author before using it on a
   workspace whose state/ is already filled in. `--refresh <path>`
   (repeatable) updates ONLY the named template paths with backups — the
   right tool for porting template updates (e.g. `--refresh AGENTS.md`)
   into an existing workspace. `--steward` seeds `.project-steward/` via
   the project-steward CLI when it is on PATH; otherwise it prints the
   agent-route note (Project Steward plugin detected) or a no-channel
   warning — relay that warning to the author.
2. If the directory was empty (a fresh prepared folder), propose the
   initial commit the script skips:
   `chore: initialize paper workspace from paperforge template`.
3. If the script reported \documentclass candidates, ask the author which
   file is the main manuscript and record the answer (AGENTS.md §10).
4. Relay next steps: "Start the intake interview.", plus the optional
   Project Steward init (workspace AGENTS.md §12 answer key) if steward is
   installed.
