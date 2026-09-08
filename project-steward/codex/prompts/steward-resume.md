Resume this Project Steward managed project from repo files only (never
from native session history). If the session-resume skill is installed,
follow it; condensed protocol:

1. Read .project-steward/WORKFLOW.md when present. `project-steward resume --agent codex --json` if installed; otherwise
   read .project-steward/HANDOFF.md (front matter + body), PROGRESS.md
   top entry, `git log --oneline -5`, `git status`, PLAN.md current
   milestone, QUESTIONS.md open items.
2. Crash check - an active runtime/session.json marker by itself is advisory;
   report it from `runtime_notes` without starting recovery. The previous
   session was abnormal if: handoff says session_status: active; relevant tool
   activity or commits/dirty files postdate the handoff; or a git
   merge/rebase/cherry-pick is in progress. If so, reconstruct from git
   diff/log + runtime logs and
   label claims "(inferred)"; update the handoff only after the user
   confirms. Write the reconstruction in plain, factual language. If a
   `humanizer` skill is available, apply it only to the new prose and preserve
   every fact and inference label.
3. Recap to the user in <=15 lines (done last time, current task, git
   state, next steps, blockers, crash note) and confirm the next step.
Resume is read-only on committed files - do not rewrite HANDOFF.md at
session start.

With an external backend, use its task view and the dated PLAN.md overview.
If access fails, preserve the last verified overview and report the limitation;
do not present Markdown checkbox counts as external task totals.
