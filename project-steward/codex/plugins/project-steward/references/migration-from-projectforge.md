# Migrating from Projectforge (v0.1)

`project-steward migrate` (approval-gated; `--yes` for non-interactive):

1. Backs up `.projectforge/` to
   `.project-steward/migration-backup-projectforge/` (gitignored).
2. Moves PROJECT/PLAN/PROGRESS/HANDOFF/DECISIONS into
   `.project-steward/`, rewriting the product name and state-dir paths
   inside those generated files only; `journal/` is preserved at
   `runtime/journal-legacy/`.
3. Converts the shell-style `config` (AUTO_HANDOFF_MODE,
   AUTO_HANDOFF_COOLDOWN_MIN, AUTO_HANDOFF_MIN_EDITS, COMMIT_POLICY) into
   `config.toml`, and creates `state.json` + `backend.json`.
4. In AGENTS.md: converts any `PROJECTFORGE:BEGIN/END` markers, replaces
   the legacy "Agent session protocol (Projectforge)" heading section
   with the new `agent-session-protocol` managed block, and touches
   nothing outside those regions. A diff is printed.
5. Refreshes the managed `.gitignore` block (removing `.projectforge`
   entries), deletes the legacy directory (backup + git history preserve
   it), and appends a PROGRESS.md entry.

The deprecated `projectforge` console command remains as a warning
wrapper that delegates to `project-steward`. Claude Code users should
also update the plugin (the marketplace/plugin name is now
`project-steward`; `/projectforge:*` commands become
`/project-steward:*`).
