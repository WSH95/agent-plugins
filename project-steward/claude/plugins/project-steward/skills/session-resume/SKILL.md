---
name: session-resume
description: Resume work in a Project Steward managed project. Use at the START of any session in a repo containing .project-steward/ (or when the user says "resume", "continue", "where were we", "pick up where we left off", "what's the status", or switches from another tool/device). Reads repo-resident state, recaps last session, detects crashed or unclosed sessions from git evidence and runtime markers, and reconstructs missing handoffs. Never relies on Claude Code or Codex native session history.
---

# Session resume

Continuity comes from files in git, not from any tool's native history.
The user may arrive from Codex, from another device, or after a crash.

## 1. Read state (in this order)

Prefer `project-steward resume --agent <tool> --json` — it claims the
session in `.project-steward/runtime/` (gitignored, so **resuming never
dirties the working tree**) and returns the recap plus crash signals.

Without the CLI, read: `HANDOFF.md` front matter and body →
`PROGRESS.md` top entry → `git log --oneline -5` and `git status` →
`PLAN.md` current milestone → `QUESTIONS.md` open items → the task
backend's ready view if one is adopted (e.g. `bd ready`).

## 2. Detect abnormal termination

Treat the previous session as crashed/unclosed if ANY hold:
- `HANDOFF.md` front matter says `session_status: active`;
- `runtime/session.json` on this device is `active` with no close event;
- tool actions were logged after the handoff's last update;
- dirty files or new commits exist that the handoff does not mention;
- a git merge/rebase/cherry-pick is in progress.

## 3. Reconstruct if crashed

Rebuild the picture from evidence: `git diff` + `git log` since the
handoff's `last_commit`, `runtime/activity.log`, and
`runtime/last_snapshot.md`. State plainly that the last session did not
close, and label every rebuilt claim **"(inferred)"**. Propose updating
`HANDOFF.md` with the reconstruction **after** the user confirms — do not
silently rewrite history you did not witness.

## 4. Recap to the user (≤ 15 lines, before any work)

```
Resuming <project> — last session <when> by <agent/tool>.
Done last time: ...
Current milestone/task: ...
Git: branch X @ sha, N dirty files [/ MERGE IN PROGRESS]
Next steps (from handoff): 1) ... 2) ...
Blockers / open questions: ...
[If crashed] Last session did not close; reconstructed (inferred): ...
Continue with step 1, or adjust?
```

## Anti-patterns

- Re-reading the whole codebase when the handoff already scopes the work.
- Starting to code before the recap.
- Rewriting `HANDOFF.md` at session start (that is wrap-up's job; resume
  is read-only on committed files).
- Trusting native `--resume` history over the repo state when they
  disagree — files win.
- Ignoring a concurrent fresh claim: if another device/agent looks
  active (recent heartbeat elsewhere, unexpected fresh commits), warn the
  user before editing.
