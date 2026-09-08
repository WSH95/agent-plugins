---
description: Initialize a Project Steward project by surveying the repo, interviewing the user, and generating its instruction and state files.
---

Follow the **project-init** skill end to end: detect existing state
run the read-only survey
(`project-steward survey --json` if available), interview the user about
load-bearing unknowns only, preview with `project-steward init ...
--dry-run` and paste the full AGENTS.md draft into your visible reply
BEFORE asking approval (dialogs and hidden thinking are not review
surfaces), apply via the same flags with `--yes`, populate PROJECT.md, PLAN.md, and the full HANDOFF.md body from verified
survey/interview facts. Include WORKFLOW.md and Codex file previews. New
projects default to automatic local milestone commits; follow the chosen
commit policy. Codex setup is included unless --no-codex-hooks is selected;
project trust and /hooks review remain required.
$ARGUMENTS
