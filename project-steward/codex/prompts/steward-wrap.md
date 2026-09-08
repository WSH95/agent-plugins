Wrap up this Project Steward session so another agent can continue without
the previous chat. If the session-handoff skill is installed, follow it;
condensed protocol:

1. Rewrite .project-steward/HANDOFF.md body: ## Now, ## In flight
   (cross-check every dirty file in `git status`), ## Next steps
   (numbered, executable by a stranger), ## Blockers, ## Key files,
   ## Tried and rejected, ## Warnings.
2. Write plain, factual notes. If a `humanizer` skill is available, apply it
   only to the changed prose and preserve facts, required headings, and file
   structure.
3. Update tasks in the selected backend (PLAN.md for Markdown), plus
   DECISIONS.md, QUESTIONS.md, RISKS.md, VERIFY.md. With external backends,
   refresh PLAN.md's dated overview of active, blocked, next, and recent task
   IDs. If access fails, retain and qualify the last verified overview and
   add an executable reconciliation step. Keep the full handoff in all cases.
4. `project-steward wrap --summary "one-line summary"` (sets
   session_status: closed, appends PROGRESS.md, prints warnings) - or do
   those steps manually, newest-first in PROGRESS.md.
5. Follow config.toml commit_policy: auto commits coherent verified code,
   tests, task artifacts, and project records together without another question;
   ask proposes that concrete commit; never skips commits and nudges. Review
   the diff/index, select explicit paths/hunks, and preserve unrelated changes.
   If checks fail or ownership is unclear, explain the skipped code commit.
   wrap --commit covers stewardship files only; verify its result. An
   uncommitted handoff cannot travel via Git. Never push.
