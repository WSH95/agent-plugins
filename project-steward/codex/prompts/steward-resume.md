Resume this Project Steward managed project from repo files only (never
from native session history). If the session-resume skill is installed,
follow it; condensed protocol:

1. `project-steward resume --agent codex --json` if installed; otherwise
   read .project-steward/HANDOFF.md (front matter + body), PROGRESS.md
   top entry, `git log --oneline -5`, `git status`, PLAN.md current
   milestone, QUESTIONS.md open items.
2. Crash check - previous session was abnormal if: handoff says
   session_status: active; runtime/session.json is active; tool activity
   or commits/dirty files postdate the handoff; git merge/rebase in
   progress. If so, reconstruct from git diff/log + runtime logs and
   label claims "(inferred)"; update the handoff only after the user
   confirms.
3. Recap to the user in <=15 lines (done last time, current task, git
   state, next steps, blockers, crash note) and confirm the next step.
Resume is read-only on committed files - do not rewrite HANDOFF.md at
session start.
