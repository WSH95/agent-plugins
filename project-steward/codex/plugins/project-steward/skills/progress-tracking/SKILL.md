---
name: progress-tracking
description: Keep Project Steward state current DURING work in any repo with .project-steward/. Use continuously in managed projects - when a task is completed or started, a plan changes, a decision is made, a validation run finishes, discovered work appears, or roughly every 30-45 minutes of focused work. Covers PLAN/PROGRESS/DECISIONS/QUESTIONS/RISKS updates, git commit nudges at semantic checkpoints, task-backend delegation, and the strict guardrails for editing AGENTS.md or CLAUDE.md.
---

# Progress tracking

Update at semantic boundaries — not after every edit, and never only at
session end.

## Event → action

| Event | Action |
| --- | --- |
| Task finished | Check it off in `PLAN.md` (or close it in the adopted backend) |
| Task started / blocked | Note it; blockers also go to `HANDOFF.md ## Blockers` |
| Plan changed | Edit `PLAN.md`; one-line `PROGRESS.md` entry saying why |
| Decision made | `DECISIONS.md` ADR-lite entry (context → decision → consequences) |
| Question can't be answered from repo | `QUESTIONS.md` `- [ ]` item — never guess |
| New risk / risk changed | `RISKS.md` row |
| Validation ran | Update `VERIFY.md` "last verified"; record result in `PROGRESS.md` |
| Discovered work | Backlog it (PLAN.md "Later" or the backend) — don't silently expand scope |
| Tests green after a chunk / ~30–45 min elapsed / risky step ahead | Checkpoint + commit nudge |

`project-steward checkpoint --note "..."` performs the PROGRESS append +
front-matter refresh in one deterministic step.

## Commit nudges

Propose (don't nag — if declined, wait for the next boundary):
Conventional Commits (`feat:`, `fix:`, `chore:` ...), include
`.project-steward/` in the same commit, tag milestone completions.
Respect `[git] commit_policy` in `config.toml`: `ask` = propose only,
`auto` = may run `wrap --commit`/`git commit` for steward files without
asking, `never` = stay silent. **Never push without explicit approval.**

## Task-backend delegation

If `backend.json` names an external backend (beads, Backlog.md, CCPM,
Taskmaster, Spec Kit, GitHub Issues) or its artifacts exist
(`.beads/`, `backlog/`, `.claude/epics/`, `.taskmaster/`, `.specify/`):
that backend owns fine-grained tasks; `PLAN.md` holds milestones + a
pointer. **Never maintain two task lists.** Suggest
`project-steward backend recommend` when `PLAN.md` outgrows raw Markdown
(> 25 open tasks, ≥ 5 blockers, multi-agent work, or repeated PLAN.md
merge conflicts).

## AGENTS.md / CLAUDE.md guardrails (high-risk files)

- Never edit silently. Show a diff, get explicit approval, record the
  change in `DECISIONS.md`.
- Edit only inside `PROJECT-STEWARD` managed blocks; user prose is
  untouchable.
- Keep AGENTS.md < 300 lines; CLAUDE.md stays a thin `@AGENTS.md`
  adapter. Progress logs and TODO dumps never belong in either file.

## Doc-drift audit (on request or via /project-steward:audit)

Re-verify AGENTS.md claims against reality: run each documented
build/test/lint command (with permission), check paths still exist, check
`PLAN.md` matches the adopted backend, then run
`project-steward doctor` and fix or report drift.
