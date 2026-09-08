Initialize this repository (or empty directory) as a Project Steward
managed project. If the project-init skill is installed, follow it; the
condensed protocol is below.

1. Detect: existing .project-steward/ -> offer audit/re-init; empty dir
   -> run the discovery interview (purpose, users, non-goals, stack, deployment,
   testing, license, security, first milestone, backend, git-init).
2. Survey read-only (`project-steward survey --json` if installed;
   otherwise README, manifests, CI, git log/status, tree). Never execute
   project scripts. Separate confident facts from open questions.
3. Interview: at most 2 rounds of 3-5 batched, load-bearing questions.
   Record unanswerables in .project-steward/QUESTIONS.md - never guess.
4. Write plain, factual project prose. If a `humanizer` skill is available,
   apply it only to the new text and preserve all facts and document structure.
5. Preview `project-steward init ... --backend <selected-backend>
   --commit-policy <auto|ask|never> --dry-run`. Show the complete AGENTS.md
   draft (below 35 lines: identity, stack, commands, and a required-reading
   pointer to .project-steward/WORKFLOW.md), plus workflow and Codex file diffs.
   After approval, apply with the same flags and --yes. Populate PROJECT.md,
   PLAN.md, and the full HANDOFF.md body from survey/interview facts. External
   backends retain task authority; PLAN.md has milestone goals and a dated
   overview of active, blocked, next, and recent task IDs. Label unknowns and
   retain the last verified overview if backend access fails. CLAUDE.md imports
   @AGENTS.md. Initialization is incomplete until the document bodies are useful.
6. Git: offer git init when absent. New projects default to auto: commit
   coherent verified work and project records using reviewed paths/hunks;
   preserve unrelated changes. Existing policies remain unchanged; ask means
   propose first, never means no commits or nudges. Never push. Codex files are
   included by default (--no-codex-hooks opts out); preserve existing config.
   Report unsupported hook setup. The CLI must be on PATH and Codex project
   trust and /hooks review are still required; file creation is not activation.
7. Summarize in <=10 lines.
