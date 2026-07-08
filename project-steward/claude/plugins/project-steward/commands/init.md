---
description: Initialize this repo (or empty directory) as a Project Steward managed project — survey, interview, then generate AGENTS.md + CLAUDE.md + .project-steward/ with approval gates.
---

Follow the **project-init** skill end to end: detect existing state
(including legacy .projectforge/), run the read-only survey
(`project-steward survey --json` if available), interview the user about
load-bearing unknowns only, preview with `project-steward init ...
--dry-run` and paste the full AGENTS.md draft into your visible reply
BEFORE asking approval (dialogs and hidden thinking are not review
surfaces), apply via the same flags with `--yes`, then offer git
init/commit.
$ARGUMENTS
