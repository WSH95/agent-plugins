---
name: progress-tracking
description: Keep Project Steward state current DURING work in any repo with .project-steward/. Use continuously in managed projects - when a task is completed or started, a plan changes, a decision is made, a validation run finishes, discovered work appears, or roughly every 30-45 minutes of focused work. Covers PLAN/PROGRESS/DECISIONS/QUESTIONS/RISKS updates, git commit nudges at semantic checkpoints, task-backend delegation, and the strict guardrails for editing AGENTS.md or CLAUDE.md.
---

# Progress tracking

Update at semantic boundaries — not after every edit, and never only at
session end.

When writing project state, follow
`../../references/documentation-style.md`. Apply its rules only to new or
changed prose. Use the optional `humanizer` pass when that skill is available,
then verify that the rewrite preserved every fact and structural field.

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
| Tests green after a chunk / ~30–45 min elapsed / risky step ahead | Refresh changed records + follow commit policy |

`project-steward checkpoint --note "..."` performs the PROGRESS append +
front-matter refresh in one deterministic step. It does not update the
HANDOFF.md body or query task backends. Refresh Now / In flight / Next steps /
Blockers yourself when they change; no-op checkpoints should leave files alone.

## Milestone commits

Read `[git] commit_policy` in config.toml. New projects default to `auto`;
existing preferences remain in force. After a coherent task, fix, tested
refactor, or milestone, run relevant checks and review both the working diff
and Git index. Update project records, then follow the policy:

- `auto`: commit related code, tests, task artifacts, and `.project-steward/`
  records together without asking again. Use Conventional Commits and explicit
  paths/hunks; preserve unrelated and pre-existing work. If ownership is unclear
  or checks fail, explain the skipped code commit and leave an accurate handoff.
- `ask`: prepare the same concrete commit and ask before committing. If declined,
  wait for the next meaningful boundary before proposing another.
- `never`: do not commit or nudge.

Use ordinary Git commands for feature commits. For whole-file commits with
unrelated changes already staged, use `git commit --only -m "..." -- <paths>`
so those staged changes remain untouched. If a file mixes user and agent changes
and the intended hunks cannot be isolated safely, skip the automatic commit. `wrap --commit` handles only
stewardship files and refuses unrelated staged work. Do not create empty or
clock-driven commits. Hooks never commit. Never push without explicit approval.

## Task-backend overview

Read backend.json for the selected backend; detected artifacts alone do not
change task ownership. When an external backend owns tasks, update it first,
then refresh PLAN.md's milestone goals and focused overview: active work,
blocked work, next tasks, and recent completions, with task IDs and a last-reviewed
date. Keep the overview concise; it is a summary, not an independently edited
backlog. Reflect changed current work and blockers in HANDOFF.md as well.
If the backend is unavailable, preserve its last verified overview, label the
access limitation, and add an executable reconciliation step. Do not mark tasks
completed from guesses or overwrite known progress with an empty list.

Suggest `project-steward backend recommend` when raw Markdown outgrows its role
(> 25 open tasks, ≥ 5 blockers, multi-agent work, or repeated PLAN.md conflicts).

## AGENTS.md / CLAUDE.md guardrails (high-risk files)

- Never edit silently. Show a diff, get explicit approval, record the
  change in `DECISIONS.md`.
- Edit only inside `PROJECT-STEWARD` managed blocks; user prose is
  untouchable.
- Keep Project Steward's generated `AGENTS.md` contribution compact; a new
  scaffold stays below 35 lines before user additions and requires reading
  `.project-steward/WORKFLOW.md` for the detailed protocol. `CLAUDE.md` remains a
  thin `@AGENTS.md` adapter. Progress logs and TODO dumps belong in project
  state, not either instruction file.

## Doc-drift audit (on request or via /project-steward:audit)

Re-verify AGENTS.md claims against reality: run each documented
build/test/lint command (with permission), check paths still exist, check
`PLAN.md` matches the adopted backend, then run
`project-steward doctor` and fix or report drift.
