---
name: project-init
description: Initialize any repository or empty directory as an agent-managed Project Steward project. Use when the user says "init", "initialize this project", "set up project management", "make this agent-managed", "create AGENTS.md/CLAUDE.md", "set up steward", or when starting substantial work in a repo that has no .project-steward/ directory. Surveys the repo, interviews the user about unclear or high-impact assumptions, then generates AGENTS.md (canonical), a CLAUDE.md adapter, and .project-steward/ state — with approval gates.
---

# Project init

Goal: a repository that any agent (Claude Code, Codex, Grok, other) can pick up
cold. Interview first, generate second, approve before writing.

## Phase 0 — Detect state

- `.project-steward/` exists → offer **audit** (run `project-steward
  doctor`) or **re-init** (only fills gaps; never overwrites state files).
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

Ask at most 2 rounds of 3–5 batched questions (use `ask_user_question`
or AskUserQuestion when available). Only ask what the survey could not answer or what requires
user intent: primary focus, build/test/lint commands, conventions to
enforce, task-backend preference (delegate the explanation to the
backend-broker skill), git policy, first milestone. Present automatic local
milestone commits as the default for new projects; preserve existing settings.
Codex setup is included for every project, with --no-codex-hooks to opt out.

Empty project: run a discovery interview instead — purpose, users,
problem, non-goals, target/forbidden stack, deployment, data needs,
testing expectations, license, security/privacy constraints, first
milestone, backend preference, git-init preference, agent-autonomy
preference. If a `brainstorming` skill (e.g. Superpowers) is installed,
defer idea refinement to it and resume here with its output.

Never guess an unanswered load-bearing question — record it in
`.project-steward/QUESTIONS.md` instead.

## Phase 3 — Generate (approval gated)

1. Read `../../references/documentation-style.md` before drafting project
   prose. If a `humanizer` skill is available, use its optional pass on the
   new prose before showing or writing it. Preserve every fact, command, link,
   placeholder, and Markdown structure.
2. Map the interview answers onto init flags and preview without writing:
   `project-steward init --project-name "..." --one-liner "..."
   --primary-language "..." --build-command "..." --test-command "..."
   --lint-command "..." --backend <selected-backend> --first-milestone "..."
   --commit-policy <auto|ask|never>
   --dry-run` — this prints the create/update/keep file plan plus full
   diffs for `AGENTS.md`, `CLAUDE.md`, and `.gitignore`, and writes
   nothing. Include the WORKFLOW.md and Codex config/hook previews.
   Existing Codex config is preserved; unsupported inline hooks or malformed
   hook JSON are reported without overwriting them. (Without the CLI: compose the same draft yourself from
   `../../src/project_steward/templates/`, preserving any existing user
   content and editing only inside managed blocks.) A representative new
   `AGENTS.md` stays below 35 lines: project identity, stack, `commands`, and
   an `agent-session-protocol` pointer requiring the agent to read
   `.project-steward/WORKFLOW.md`. Detailed stewardship and task-backend
   instructions live in that document, which also works without plugin skills.
3. Paste the complete AGENTS.md draft (fenced; or diff, if the file
   exists) and the file plan into your reply — the user-visible message
   text — BEFORE asking anything. Thinking, subagent transcripts,
   AskUserQuestion / `ask_user_question` dialogs, and collapsed tool output are not review
   surfaces: if the draft does not appear verbatim in the visible
   conversation, you may not ask for approval.
4. Get explicit approval (AskUserQuestion / `ask_user_question` is fine for the question
   itself), then apply by re-running the same flags with `--dry-run`
   replaced by `--yes`, so blocks and state files are written
   deterministically and idempotently. Then populate `PROJECT.md`, `PLAN.md`, and the entire `HANDOFF.md` body
   with survey/interview facts: purpose, milestone goals, current implementation
   state, unfinished work, blockers, validation evidence, and executable next
   steps. Record the setup and selected backend/policy in `PROGRESS.md`.
   With an external backend, PLAN.md includes a dated overview of active,
   blocked, next, and recently completed work with task IDs. Backend tasks
   remain authoritative. Identify unknowns instead of claiming no work exists.
   Initialization is incomplete until these document bodies are useful.
5. `CLAUDE.md` must stay a thin adapter that imports `@AGENTS.md`
   (Claude Code does not read AGENTS.md natively).

## Phase 4 — Git

Not a repo → ask, then assist: `git init`, review `.gitignore`
(the managed block ignores `.project-steward/runtime/`), initial commit
`chore: initialize Project Steward project management`. Already a repo →
follow the configured commit policy. Under auto, review the initialization
changes and commit related files, including `.project-steward/` and any new
`.codex/` files; under ask, propose the concrete commit. Under never, skip it.
Use explicit paths/hunks and preserve unrelated staged and unstaged changes. **Never force git init; never push.**

## Phase 5 — Summary

≤ 10 lines: what was created, what was inferred vs. asked, open
questions recorded, and the suggested next command
(`/project-steward:resume` next session; on Grok, `/session-resume` —
bare `/resume` is Grok's native session picker). For Codex, distinguish files
installed from hooks active: the CLI must be on PATH, the project trusted, and
new hooks reviewed through `/hooks`. Do not claim activation from file creation.

## Interop

- Built-in `/init` (Claude Code) or Codex init output may be used as raw
  survey input; Project Steward owns the final interview and files.
- CCPM / Spec Kit / Taskmaster / beads detected → don't duplicate their
  role; see the backend-broker skill and keep milestone goals and the focused
  dated task overview in PLAN.md. If the backend cannot be read, retain its
  last verified overview and record the access limitation and next check.
