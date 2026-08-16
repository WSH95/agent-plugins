---
description: Create a new paper workspace from the bundled Paperforge template (fresh path) and initialize git.
argument-hint: "[--steward] /path/to/my-paper"
---

Create a new Paperforge paper workspace at the destination the author gives
you ($ARGUMENTS; ask if missing).

1. The destination must NOT exist yet and its parent must exist (the script
   refuses otherwise). For an existing — even empty — directory, use
   /paperforge:adopt-paper instead. Pass `--steward` through if the author
   wants the workspace born steward-managed (the script seeds
   `.project-steward/` when the project-steward CLI is on PATH; without
   it, it prints the agent-route note when the Project Steward plugin is
   detected, or a no-channel warning — relay that warning to the author).
2. Run the bundled script (the single source of scaffolding logic):

   bash "${GROK_PLUGIN_ROOT}/new-paper.sh" "<destination>"

   or, when that variable is empty, `"${CLAUDE_PLUGIN_ROOT}/new-paper.sh"`.
   If neither ${GROK_PLUGIN_ROOT} nor ${CLAUDE_PLUGIN_ROOT} was expanded
   in this text, resolve the newest directory named `paperforge` that
   contains both `new-paper.sh` and `adopt-paper.sh` under
   `~/.grok/installed-plugins/` or `~/.grok/plugins/` (Grok Build),
   `~/.claude/plugins/cache/*/paperforge/*/` (Claude Code, any
   marketplace), or `~/.codex/plugins/cache/*/paperforge/*/` (Codex),
   then run its new-paper.sh. Never re-implement the copy logic yourself.
3. Relay the script's next steps: optional private remote for
   cross-machine sync; the first prompt "Start the intake interview."; and
   the optional Project Steward init (workspace AGENTS.md §12 has the
   answer key) if steward is installed.
