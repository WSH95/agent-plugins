Wrap up this Project Steward session for a zero-context successor. If the
session-handoff skill is installed, follow it; condensed protocol:

1. Rewrite .project-steward/HANDOFF.md body: ## Now, ## In flight
   (cross-check every dirty file in `git status`), ## Next steps
   (numbered, executable by a stranger), ## Blockers, ## Key files,
   ## Tried and rejected, ## Warnings.
2. Update PLAN.md checkboxes, DECISIONS.md, QUESTIONS.md, RISKS.md,
   VERIFY.md as applicable.
3. `project-steward wrap --summary "one-line summary"` (sets
   session_status: closed, appends PROGRESS.md, prints warnings) - or do
   those steps manually, newest-first in PROGRESS.md.
4. Propose a Conventional Commit including .project-steward/ per
   config.toml commit_policy. An uncommitted handoff cannot cross
   devices. Never push.
