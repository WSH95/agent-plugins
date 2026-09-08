---
name: session-handoff
description: Write a complete session handoff in a Project Steward managed project. Use when the user says they are pausing, leaving, wrapping up, done for today, switching tools (Claude Code, Codex, or Grok) or devices, ending the session, or asks to "hand off" / "save state" — and before any planned risky operation. Also used by the Stop-hook auto-checkpoint. Rewrites .project-steward/HANDOFF.md for a zero-context successor, appends PROGRESS.md, and follows the configured commit policy.
---

# Session handoff

Write for a stranger with zero context — possibly a different model on a
different machine. If it is not in the files, it did not happen.

Before writing, read `../../references/documentation-style.md`. Apply it to
the handoff text and other state entries changed in this session. If a
`humanizer` skill is available, use its optional pass before saving the files.
Keep every verified fact and all required headings.

## Full wrap (session ending)

1. **Rewrite the `HANDOFF.md` body** (front matter is handled in step 3):
   - `## Now` — one paragraph: where things stand.
   - `## In flight` — started-but-unfinished work, **cross-checked
     against `git status`**: every dirty file is either explained here or
     intentionally reverted.
   - `## Next steps` — numbered, each executable by a stranger
     ("Run X, expect Y, then Z"), most important first.
   - `## Blockers`, `## Key files` (paths + why they matter),
     `## Tried and rejected` (save the successor from dead ends),
     `## Warnings` (fragile areas, gotchas, things NOT to do).
2. **Update siblings**: close tasks in the selected backend (PLAN.md for
   Markdown). With external backends, refresh PLAN.md's dated milestone/task
   overview with active, blocked, next, and recently completed task IDs. If the
   backend is unavailable, retain the last verified overview, label the
   limitation, and add a concrete reconciliation step to HANDOFF.md. Keep the
   full handoff body and validation evidence with every backend. Record
   decisions in `DECISIONS.md`; new questions in `QUESTIONS.md`; changed
   risks in `RISKS.md`; refresh `VERIFY.md`'s "last verified" line if
   validation ran.
3. **Finalize bookkeeping**:
   `project-steward wrap --summary "one-line session summary"` — sets
   `session_status: closed`, syncs branch into the front matter,
   appends the `PROGRESS.md` entry, deliberately closes the current runtime
   claim even when a hook supplied its session ID, and prints
   dirty-file warnings plus the commit suggestion. (No CLI: do those
   steps by hand; PROGRESS.md is newest-first.)
4. **Follow the commit policy** in config.toml: under `auto`, review relevant
   checks and changes, then commit coherent code, tests, task artifacts, and
   `.project-steward/` records together without asking again. Under `ask`, propose
   that concrete commit; under `never`, skip commits and nudges. Use Conventional
   Commits and explicit paths/hunks. Preserve unrelated changes; explain skipped
   code commits when checks fail or ownership is unclear. `wrap --commit` covers
   stewardship files only, rejects unrelated staged work, and can fail; verify
   the result. An uncommitted handoff cannot travel via Git. **Never push.**

## Auto-checkpoint (mid-session, hook-triggered)

Hooks never commit. When the Stop hook blocks with a stale-handoff reason, first decide whether
project state changed. If it did, briefly update `HANDOFF.md` (Now / In flight /
Next steps) and use `project-steward checkpoint --note "..." --auto` for bookkeeping, keep
`session_status: active`, prefix the progress entry `[auto-checkpoint]`, tell
the user in one line, and stop. If nothing material changed, leave tracked
files unchanged and stop. Do not create a checkpoint only to acknowledge the
prompt. The commit that stores a completed handoff does not make that handoff
stale.

## Quality self-check

Could a competent stranger continue from `HANDOFF.md` alone, without this
conversation? If any next step needs missing context, add it. Vague
("continue the refactor") fails; concrete ("Rename `PolicyNet.forward`
callers in `train.py:120-180`; tests in `tests/test_policy.py` must stay
green") passes.
