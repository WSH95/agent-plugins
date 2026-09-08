---
name: session-resume
description: Resume work in a Project Steward managed project. Use at the START of any session in a repo containing .project-steward/ (or when the user says "resume", "continue", "where were we", "pick up where we left off", "what's the status", or switches from another tool/device). Reads repo-resident state, recaps the last session, detects unfinished work from durable and Git evidence, and reconstructs missing handoffs. Never relies on Claude Code, Codex, or Grok native session history. On Grok, invoke as /session-resume or /project-steward:resume — bare /resume is Grok's session picker.
---

# Session resume

Continuity comes from files in git, not from any tool's native history.
The user may arrive from Codex, Grok, from another device, or after a crash.

Read `.project-steward/WORKFLOW.md` when present; older projects keep the
protocol inline in AGENTS.md.

## 1. Read state (in this order)

Prefer `project-steward resume --agent <tool> --json` — it claims the
session in `.project-steward/runtime/` (gitignored, so **resuming never
dirties the working tree**) and returns the recap, crash signals, and advisory
runtime notes. If an active current marker already exists, resume reuses it,
including a marker created by a hook.

Without the CLI, read: `HANDOFF.md` front matter and body →
`PROGRESS.md` top entry → `git log --oneline -5` and `git status` →
`PLAN.md` current milestone → `QUESTIONS.md` open items → the task
backend's ready view if one is adopted (e.g. `bd ready`). For an external backend, PLAN.md is a dated overview,
not an authoritative task count. If access fails, retain the last verified
overview, report that limitation, and use HANDOFF.md for the next check.

## 2. Detect abnormal termination

An active local runtime marker alone is advisory, not proof that a prior
session ended abnormally. Report `runtime_notes` without starting recovery.
Treat the previous session as crashed/unclosed if ANY of these separate signals
hold:
- `HANDOFF.md` front matter says `session_status: active`;
- tool actions were logged after the handoff's last update;
- dirty files or new commits exist that the handoff does not mention;
- a git merge/rebase/cherry-pick is in progress.

## 3. Reconstruct if crashed

Rebuild the picture from evidence: `git diff` + `git log` since the commit
that last changed `HANDOFF.md` (reported as `handoff.last_commit` by the CLI),
`runtime/activity.log`, and
`runtime/last_snapshot.md`. State plainly that the last session did not
close, and label every rebuilt claim **"(inferred)"**. Propose updating
`HANDOFF.md` with the reconstruction **after** the user confirms — do not
silently rewrite history you did not witness.

If the user approves a reconstructed handoff, follow
`../../references/documentation-style.md` for the new text. Use the optional
`humanizer` pass when available, and keep all evidence and inference labels.

## 4. Recap to the user (≤ 15 lines, before any work)

```
Resuming <project> — last session <when> by <agent/tool>.
Done last time: ...
Current milestone/task: ...
Git: branch X @ sha, N dirty files [/ MERGE IN PROGRESS]
Next steps (from handoff): 1) ... 2) ...
Blockers / open questions: ...
[Runtime note, if present: ...]
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
