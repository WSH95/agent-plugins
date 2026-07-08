---
name: session-handoff
description: Write a complete session handoff in a Project Steward managed project. Use when the user says they are pausing, leaving, wrapping up, done for today, switching tools (Claude Code <-> Codex) or devices, ending the session, or asks to "hand off" / "save state" — and before any planned risky operation. Also used by the Stop-hook auto-checkpoint. Rewrites .project-steward/HANDOFF.md for a zero-context successor, appends PROGRESS.md, and proposes a git commit.
---

# Session handoff

Write for a stranger with zero context — possibly a different model on a
different machine. If it is not in the files, it did not happen.

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
2. **Update siblings**: check off finished `PLAN.md` tasks; record
   decisions in `DECISIONS.md`; new questions in `QUESTIONS.md`; changed
   risks in `RISKS.md`; refresh `VERIFY.md`'s "last verified" line if
   validation ran.
3. **Finalize bookkeeping**:
   `project-steward wrap --summary "one-line session summary"` — sets
   `session_status: closed`, syncs branch/commit into the front matter,
   appends the `PROGRESS.md` entry, closes the runtime claim, and prints
   dirty-file warnings plus the commit suggestion. (No CLI: do those
   steps by hand; PROGRESS.md is newest-first.)
4. **Propose the commit** per `[git] commit_policy` in `config.toml`
   (Conventional Commits; include `.project-steward/`). An uncommitted
   handoff cannot cross devices — say so if the user declines. `wrap
   --commit` performs it when policy allows. **Never push.**

## Auto-checkpoint (mid-session, hook-triggered)

When the Stop hook blocks with a stale-handoff reason: briefly update
`HANDOFF.md` (Now / In flight / Next steps) or run
`project-steward checkpoint --note "..." --auto`, keep
`session_status: active`, prefix the progress entry `[auto-checkpoint]`,
tell the user in one line, and stop. Do not start new work.

## Quality self-check

Could a competent stranger continue from `HANDOFF.md` alone, without this
conversation? If any next step needs missing context, add it. Vague
("continue the refactor") fails; concrete ("Rename `PolicyNet.forward`
callers in `train.py:120-180`; tests in `tests/test_policy.py` must stay
green") passes.
