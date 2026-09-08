---
description: Wrap up the session so another agent can continue, then update progress and follow the commit policy.
---

Follow the **session-handoff** skill (full wrap): rewrite the HANDOFF.md
body (Now / In flight cross-checked vs `git status` / numbered Next steps
/ Blockers / Key files / Tried and rejected / Warnings), update
PLAN/DECISIONS/QUESTIONS/RISKS/VERIFY as needed, then
`project-steward wrap --summary "..."` and follow the commit policy. Under auto, commit coherent verified code,
tests, task artifacts, and project records together using reviewed paths/hunks;
under ask, propose the commit; under never, skip it. Preserve unrelated work.
External backends keep task authority; refresh PLAN.md's dated overview and
the full handoff. If the backend is unavailable, retain and qualify the last
verified overview. `wrap --commit` covers stewardship files only. Never push.
$ARGUMENTS
