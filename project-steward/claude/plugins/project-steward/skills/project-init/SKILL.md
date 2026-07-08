---
name: project-init
description: Initialize any repository or empty directory as an agent-managed Project Steward project. Use when the user says "init", "initialize this project", "set up project management", "make this agent-managed", "create AGENTS.md/CLAUDE.md", "set up steward", or when starting substantial work in a repo that has no .project-steward/ directory. Surveys the repo, interviews the user about unclear or high-impact assumptions, then generates AGENTS.md (canonical), a CLAUDE.md adapter, and .project-steward/ state — with approval gates.
---

# Project init

Goal: a repository that any agent (Claude Code, Codex, other) can pick up
cold. Interview first, generate second, approve before writing.

## Phase 0 — Detect state

- `.project-steward/` exists → offer **audit** (run `project-steward
  doctor`) or **re-init** (only fills gaps; never overwrites state files).
- `.projectforge/` exists → propose `project-steward migrate` (approval
  gated) before or alongside init.
- Directory empty (no files, no git) → skip to Phase 2's empty-project
  interview.
- Existing `CLAUDE.md`, `.cursorrules`, or Copilot instructions → read
  them; their content is candidate material for AGENTS.md (ask before
  absorbing).

## Phase 1 — Survey (read-only)

Prefer the deterministic CLI: `project-steward survey --json`
(falls back to manual inspection of README, manifests, CI configs,
`git log --oneline -10`, `git status`, and the top-level tree if the CLI
is unavailable). **Never execute project scripts during the survey** —
reading only (see ../../references/security-model.md).

Sort findings into: **confident facts** (state them, don't ask),
**uncertain facts**, **missing facts**, and **risks**. If `.env` or other
sensitive files exist, note their presence but never read or summarize
their contents.

## Phase 2 — Interview (batched, load-bearing only)

Ask at most 2 rounds of 3–5 batched questions (use AskUserQuestion when
available). Only ask what the survey could not answer or what requires
user intent: primary focus, build/test/lint commands, conventions to
enforce, task-backend preference (delegate the explanation to the
backend-broker skill), git policy, first milestone.

Empty project: run a discovery interview instead — purpose, users,
problem, non-goals, target/forbidden stack, deployment, data needs,
testing expectations, license, security/privacy constraints, first
milestone, backend preference, git-init preference, agent-autonomy
preference. If a `brainstorming` skill (e.g. Superpowers) is installed,
defer idea refinement to it and resume here with its output.

Never guess an unanswered load-bearing question — record it in
`.project-steward/QUESTIONS.md` instead.

## Phase 3 — Generate (approval gated)

1. Map the interview answers onto init flags and preview without writing:
   `project-steward init --project-name "..." --one-liner "..."
   --primary-language "..." --build-command "..." --test-command "..."
   --lint-command "..." --backend markdown --first-milestone "..."
   --dry-run` — this prints the create/update/keep file plan plus full
   diffs for `AGENTS.md`, `CLAUDE.md`, and `.gitignore`, and writes
   nothing. (Without the CLI: compose the same draft yourself from
   `../../src/project_steward/templates/`, preserving any existing user
   content and editing only inside managed blocks.) Keep AGENTS.md canonical and < 150 lines:
   overview, source of truth, conventions, git policy — plus the three
   managed blocks: `commands`, `task-backend`, `agent-session-protocol`.
2. Paste the complete AGENTS.md draft (fenced; or diff, if the file
   exists) and the file plan into your reply — the user-visible message
   text — BEFORE asking anything. Thinking, subagent transcripts,
   AskUserQuestion dialogs, and collapsed tool output are not review
   surfaces: if the draft does not appear verbatim in the visible
   conversation, you may not ask for approval.
3. Get explicit approval (AskUserQuestion is fine for the question
   itself), then apply by re-running the same flags with `--dry-run`
   replaced by `--yes`, so blocks and state files are written
   deterministically and idempotently. Then edit the generated
   `.project-steward/PROJECT.md` and `PLAN.md` with the interview's real
   content.
4. `CLAUDE.md` must stay a thin adapter that imports `@AGENTS.md`
   (Claude Code does not read AGENTS.md natively).

## Phase 4 — Git

Not a repo → ask, then assist: `git init`, review `.gitignore`
(the managed block ignores `.project-steward/runtime/`), initial commit
`chore: initialize Project Steward project management`. Already a repo →
propose that commit. **Never force git init; never push.**

## Phase 5 — Summary

≤ 10 lines: what was created, what was inferred vs. asked, open
questions recorded, and the suggested next command
(`/project-steward:resume` next session).

## Interop

- Built-in `/init` (Claude Code) or Codex init output may be used as raw
  survey input; Project Steward owns the final interview and files.
- CCPM / Spec Kit / Taskmaster / beads detected → don't duplicate their
  role; see the backend-broker skill and keep PLAN.md as milestones + a
  pointer.
