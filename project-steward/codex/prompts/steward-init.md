Initialize this repository (or empty directory) as a Project Steward
managed project. If the project-init skill is installed, follow it; the
condensed protocol is below.

1. Detect: existing .project-steward/ -> offer audit/re-init; legacy
   .projectforge/ -> propose `project-steward migrate`; empty dir -> run
   the discovery interview (purpose, users, non-goals, stack, deployment,
   testing, license, security, first milestone, backend, git-init).
2. Survey read-only (`project-steward survey --json` if installed;
   otherwise README, manifests, CI, git log/status, tree). Never execute
   project scripts. Separate confident facts from open questions.
3. Interview: at most 2 rounds of 3-5 batched, load-bearing questions.
   Record unanswerables in .project-steward/QUESTIONS.md - never guess.
4. Generate with approval: show the full AGENTS.md draft (canonical,
   <150 lines, managed blocks: commands / task-backend /
   agent-session-protocol); on approval run
   `project-steward init --project-name ... --yes` (or create files from
   templates manually), then fill PROJECT.md and PLAN.md with real
   content. CLAUDE.md stays a thin @AGENTS.md adapter.
5. Git: if not a repo, ask, then assist `git init` + initial commit
   `chore: initialize Project Steward project management`. Never push.
6. Summarize in <=10 lines.
