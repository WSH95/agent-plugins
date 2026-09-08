# Session protocol

The contract that makes sessions portable across Claude Code, Codex,
Grok Build, other agents, and devices. The repository owns continuity;
native session histories are execution details.

## State model

Committed (durable, travels via git): `.project-steward/WORKFLOW.md`, `PROJECT.md`,
`PLAN.md`, `PROGRESS.md`, `HANDOFF.md`, `DECISIONS.md`, `QUESTIONS.md`,
`RISKS.md`, `VERIFY.md`, `config.toml`, `state.json`, `backend.json`,
`runtime/` is device-local and never committed.

Runtime commands and doctor use the same config normalization. Invalid known
sections, values, or types use documented safe defaults and doctor reports the
fallback; valid unrelated settings remain intact. Numeric session limits must
be nonnegative integers, and booleans do not count as integers. backend.json is
the sole authoritative task-backend identity.

Local (gitignored, device-scoped forensics): `.project-steward/runtime/`
— `session.json` (the current session claim), `activity.log` (event-based
heartbeat, rotated), `events.log`, `last_snapshot.md`, `stop_guard.json`.

**Invariant: starting or resuming a session never dirties the git
working tree.** Session claims go to runtime files; committed files
change only at semantic checkpoints and wrap-up. Resume never edits
HANDOFF.md front matter.

## Lifecycle

1. **Start**: read WORKFLOW.md when present, then HANDOFF.md -> recap -> crash
   check (see below) -> claim or reuse the runtime session. Hook: SessionStart
   injects the recap automatically.
2. **Work**: updates at semantic boundaries (see the progress-tracking
   skill's event table); PostToolUse hooks feed the activity log. Claude,
   Codex, and Grok edit tools are recognized. Shell commands supplied through
   `command` or `cmd` are treated as modifying when they contain unquoted
   redirection or chaining, even if their first command is read-only.
3. **Checkpoint**: PROGRESS append + HANDOFF front-matter refresh. Git history,
   not a self-referential front-matter field, identifies the handoff commit;
   triggered manually, by the wrap-language detector, or by the Stop
   guard. The agent also refreshes changed handoff bodies and external task
   overviews; the CLI updates metadata only.
4. **Wrap**: full HANDOFF rewrite for a zero-context successor;
   `session_status: closed`; follow commit_policy. Under auto, commit coherent
   verified work and its project records; under ask, propose it; under never,
   skip commits and nudges. Hooks never commit. Explicit CLI wrap and close
   operations close the current project marker.

Hook payloads store a session ID in the current marker when one is available.
Repeated starts for that ID reuse the marker and retain its start time.
PostToolUse heartbeats and automated SessionEnd closes apply only when their
ID owns the current marker, so a delayed event cannot change a newer session's
claim. ID-less legacy markers and hook payloads remain supported. CLI resume
reuses an active current marker, including one created by a hook. This is still
one lightweight current marker, not a session registry.

## Recovery signals

- HANDOFF front matter says `session_status: active`
- activity.log entries newer than HANDOFF.md's mtime
- dirty files or commits the handoff does not mention
- git merge/rebase/cherry-pick in progress

An active `runtime/session.json` marker by itself is advisory. Recap JSON lists
it under `runtime_notes`, not `crash_signals`, because current, repeated, and
overlapping hook delivery can all produce a live marker. Use the recovery
signals above to decide whether reconstruction is needed.

Reconstruction uses `git diff`/`git log` since the commit that last changed
`HANDOFF.md`, plus runtime logs. The CLI reports that derived commit as
`handoff.last_commit`; every rebuilt claim is labeled "(inferred)".

Git operation markers are located with `git rev-parse --git-path`, which covers
ordinary repositories and repositories whose `.git` entry is a file, including
linked worktrees and submodules.

Implicit project discovery checks managed and legacy state at each directory,
then stops at the nearest `.git` directory or file. Commands started inside an
independent nested repository therefore cannot select an enclosing project's
state. A subdirectory of a managed repository still finds that repository, and
`--root` remains the explicit override when an enclosing project is intended.

## Stop guard (Claude Code + Codex + Grok hooks)

If >= `auto_handoff_min_edits` actions occurred since the handoff's last
update and the cooldown (`auto_handoff_cooldown_min`) passed, the Stop
hook emits `{"decision": "block", "reason": ...}` once, instructing a
brief auto-checkpoint. Each activity batch is handled once. If project state
did not change, the agent leaves tracked files unchanged. `stop_hook_active` /
`stopHookActive` prevent same-turn loops. Grok session-teardown Stops
(`reason` `shutdown` or `channel_closed`) are ignored. Modes: `block`
(default) / `remind`
(`systemMessage` only; weaker on Grok) / `off`. Worst case after a hard
crash: one cooldown window of work, still journaled in runtime logs.
Malformed session configuration falls back to these defaults instead of
silently disabling the guard; doctor reports the invalid fields.

## External task backends

backend.json names the task source of truth. PLAN.md still explains milestone
goals and gives a dated overview of active, blocked, next, and recently completed
work with task IDs. HANDOFF.md always records the complete session context and
validation evidence. Update the backend first, then the overview and handoff.
If access fails, retain the last verified overview, label the limitation, and
record an executable reconciliation step. Recap JSON includes task_backend;
open_tasks remains a count of Markdown checkboxes, not external backend totals.
