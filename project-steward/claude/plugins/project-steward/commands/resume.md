---
description: Resume this project from repo-resident state — recap the last session, detect crashed/unclosed sessions, reconstruct if needed.
---

Follow the **session-resume** skill: run
`project-steward resume --agent claude --json` (or read
.project-steward/HANDOFF.md, PROGRESS.md, git log/status manually), give
the ≤15-line recap, investigate any abnormal-termination signals before
editing, and confirm the next step with the user. Resume never modifies
committed files. $ARGUMENTS
