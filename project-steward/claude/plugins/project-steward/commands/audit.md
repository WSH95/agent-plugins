---
description: Audit steward docs against reality — stale commands, drifted paths, plan/backend mismatches, doctor checks.
---

Follow the **progress-tracking** skill's doc-drift audit: re-verify every
command documented in AGENTS.md (ask before running), check referenced
paths exist, check PLAN.md against the adopted backend, run
`project-steward doctor`, then propose fixes as diffs (AGENTS.md/CLAUDE.md
changes need explicit approval + a DECISIONS.md entry). $ARGUMENTS
