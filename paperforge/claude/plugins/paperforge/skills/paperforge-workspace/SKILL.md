---
name: paperforge-workspace
description: Create, adopt, refresh, or steward-seed a Paperforge paper workspace using the bundled new-paper.sh and adopt-paper.sh scripts. Use whenever the author asks to make a new paper repo, adopt an existing LaTeX repo, refresh Paperforge scaffolding, run Paperforge setup, or use --steward with Paperforge. This is the cross-tool path for Claude Code, Codex, and Grok Build; Claude slash commands are convenience aliases only.
---

# Paperforge Workspace Setup

Create or update a paper workspace by running the bundled Paperforge scripts.
Never reimplement the copy logic in the agent; the scripts are the contract.

## What This Skill Covers

- New workspace: `new-paper.sh [--steward] /path/to/new-paper`
- Existing or prepared directory: `adopt-paper.sh [--force|--steward] /path`
- Targeted refresh: `adopt-paper.sh --refresh <template-path> /path`

Use `paper-intake` after scaffolding when the author is ready to start the paper.

## Resolve the Plugin Root

Use the first available route:

1. If the skill loader exposes this `SKILL.md` path, the plugin root is two
   directories above it.
2. Use `${GROK_PLUGIN_ROOT}` when set (Grok Build), otherwise
   `${CLAUDE_PLUGIN_ROOT}` (Claude Code slash commands).
3. If neither variable is available, search the installed plugin trees for a
   directory named `paperforge` containing both `new-paper.sh` and
   `adopt-paper.sh`, then choose the newest matching entry:
   `~/.grok/installed-plugins/` (Grok `plugin install` copies) and
   `~/.grok/plugins/` (optional extra plugin dirs),
   `~/.claude/plugins/cache/*/paperforge/*/` (Claude Code),
   `~/.codex/plugins/cache/*/paperforge/*/` (Codex).
4. If the author is running from a source checkout, use the checkout's `plugin/`
   directory.

Stop and ask only if multiple plausible roots remain after inspection.

## New Paper

Run:

```bash
bash "<plugin-root>/new-paper.sh" [--steward] "/path/to/new-paper"
```

The destination must not already exist, and its parent must exist. If the author
wants an existing or empty prepared directory, use adopt instead.

Relay the script's next steps exactly enough that the author knows where to `cd`,
how to start their agent, and that the first paper prompt is:

```text
Start the intake interview.
```

## Adopt Existing Directory

Run:

```bash
bash "<plugin-root>/adopt-paper.sh" [--force|--steward] "/path/to/existing"
```

Use `--force` only after warning that Paperforge scaffolding files are
overwritten with timestamped backups. The script never moves or overwrites the
author's manuscript directory.

If the script reports documentclass candidates, ask the author which `.tex` file
is the main manuscript and record that answer in the paper workspace.

## Refresh Existing Scaffolding

Run:

```bash
bash "<plugin-root>/adopt-paper.sh" --refresh AGENTS.md "/path/to/workspace"
```

Allow repeated `--refresh <path>` arguments when the author names multiple
template paths. Warn before refreshing `state/` paths because they contain
author-owned paper content.

## Project Steward

Pass `--steward` through only when the author asks for Project Steward seeding.
If the CLI is unavailable, the scripts print either an agent-plugin route or a
no-channel warning. Relay that warning instead of trying to seed by hand.
