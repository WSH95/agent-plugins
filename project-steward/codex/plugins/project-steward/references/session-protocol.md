# Session protocol

The contract that makes sessions portable across Claude Code, Codex,
other agents, and devices. The repository owns continuity; native session
histories are execution details.

## State model

Committed (durable, travels via git): `.project-steward/PROJECT.md`,
`PLAN.md`, `PROGRESS.md`, `HANDOFF.md`, `DECISIONS.md`, `QUESTIONS.md`,
`RISKS.md`, `VERIFY.md`, `config.toml`, `state.json`, `backend.json`,
optional `sessions/*.md`.

Local (gitignored, device-scoped forensics): `.project-steward/runtime/`
— `session.json` (active-session claim), `activity.log` (event-based
heartbeat, rotated), `events.log`, `last_snapshot.md`, `stop_guard.json`.

**Invariant: starting or resuming a session never dirties the git
working tree.** Session claims go to runtime files; committed files
change only at semantic checkpoints and wrap-up. (This fixes a
Projectforge v0.1 flaw where resume edited HANDOFF.md front matter.)

## Lifecycle

1. **Start**: read HANDOFF.md -> recap -> crash check (see below) ->
   claim runtime session. Hook: SessionStart injects the recap
   automatically.
2. **Work**: updates at semantic boundaries (see the progress-tracking
   skill's event table); PostToolUse hooks feed the activity log.
3. **Checkpoint**: PROGRESS append + HANDOFF front-matter refresh;
   triggered manually, by the wrap-language detector, or by the Stop
   guard.
4. **Wrap**: full HANDOFF rewrite for a zero-context successor;
   `session_status: closed`; commit proposal.

## Crash detection signals (any one suffices)

- HANDOFF front matter `session_status: active`
- runtime/session.json active with no close event
- activity.log entries newer than HANDOFF.md's mtime
- dirty files or commits the handoff does not mention
- git merge/rebase/cherry-pick in progress

Reconstruction uses `git diff`/`git log` since `last_commit` plus runtime
logs; every rebuilt claim is labeled "(inferred)".

## Stop guard (Claude Code + Codex hooks)

If >= `auto_handoff_min_edits` actions occurred since the handoff's last
update and the cooldown (`auto_handoff_cooldown_min`) passed, the Stop
hook emits `{"decision": "block", "reason": ...}` once, instructing a
brief auto-checkpoint. `stop_hook_active` input prevents loops; modes:
`block` (default) / `remind` (systemMessage only) / `off`. Worst case
after a hard crash: one cooldown window of work, still journaled in
runtime logs.
