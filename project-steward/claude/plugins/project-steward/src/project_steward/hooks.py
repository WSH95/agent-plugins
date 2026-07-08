"""Cross-agent hook dispatcher: `project-steward hook <event> --agent X`.

One Python entry point serves both Claude Code and Codex lifecycle hooks
(their stdin/stdout JSON contracts are near-identical by design). Events:

  session-start        SessionStart      -> inject recap as additionalContext
  post-tool-use        PostToolUse       -> heartbeat + activity log (silent)
  user-prompt-submit   UserPromptSubmit  -> wrap-language detector
  stop                 Stop              -> stale-handoff guard (block/remind)
  pre-compact          PreCompact        -> forensic snapshot (Claude)
  session-end          SessionEnd        -> snapshot + close marker (Claude)

Contract: hooks NEVER fail loudly. Any internal error -> exit 0, no output.
Blocking uses JSON `{"decision": "block", "reason": ...}` on stdout with
exit 0 (valid for both agents' Stop events), never exit code 2.
"""
from __future__ import annotations

import json
import sys
import time

from . import sessions
from .paths import (find_project_root, has_legacy_state, is_steward_project,
                    runtime_dir)
from .state import (load_config, read_json, utcnow_iso, write_json_atomic)

WRAP_PHRASES = [
    "wrap up", "wrapping up", "wrap this up", "pause here", "pausing",
    "stopping for", "stop for today", "stop for now", "end the session",
    "end session", "ending the session", "call it a day", "sign off",
    "signing off", "hand off", "switch to codex",
    "switch to claude", "switching to", "continue tomorrow",
    "pick this up later", "that's all for", "done for today", "i'm leaving",
    "have to go", "gotta go",
]

# Prompts containing these are harness-injected (task notifications,
# reminders, local-command echoes), not the user speaking.
HARNESS_MARKERS = ("<task-notification>", "<system-reminder>",
                   "<local-command", "<command-name>")


def _read_stdin_json():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _emit(obj):
    try:
        sys.stdout.write(json.dumps(obj))
        sys.stdout.flush()
    except Exception:
        pass


def _additional_context(event_name, text):
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        }
    }


# --------------------------------------------------------------------------
# Event handlers
# --------------------------------------------------------------------------

def _handle_session_start(root, agent, payload):
    if not is_steward_project(root):
        if has_legacy_state(root):
            _emit(_additional_context(
                "SessionStart",
                "A legacy .projectforge/ directory was found. Run "
                "`project-steward migrate` (asks for approval) to upgrade it "
                "to .project-steward/, then follow the session-resume skill.",
            ))
        return
    previous, _record = sessions.claim_session(root, agent)
    recap = sessions.build_recap(root, runtime_record=previous)
    text = sessions.format_recap(recap)
    if previous.get("status") == "active" and previous.get("host"):
        text += (
            "\nNote: a previous runtime claim on this device (%s) was still "
            "marked active." % previous.get("agent", "?")
        )
    text += (
        "\nACTION REQUIRED: follow the session-resume skill — give the user "
        "this recap, investigate any abnormal-termination signals before "
        "editing, and do not rewrite HANDOFF.md at session start."
    )
    sessions.log_event(root, "session-start", agent)
    _emit(_additional_context("SessionStart", text))


def _handle_post_tool_use(root, agent, payload):
    if not is_steward_project(root):
        return
    tool = payload.get("tool_name", "tool")
    tool_input = payload.get("tool_input", {}) or {}
    detail = (
        tool_input.get("command")
        or tool_input.get("file_path")
        or tool_input.get("path")
        or ""
    )
    sessions.record_activity(root, tool, detail)


def _handle_user_prompt_submit(root, agent, payload):
    if not is_steward_project(root):
        return
    prompt = (payload.get("prompt") or "").lower()
    if any(marker in prompt for marker in HARNESS_MARKERS):
        return
    if any(phrase in prompt for phrase in WRAP_PHRASES):
        _emit(_additional_context(
            "UserPromptSubmit",
            "Project Steward: the user appears to be ending or pausing the "
            "session. Before finishing, follow the session-handoff skill "
            "(rewrite .project-steward/HANDOFF.md for a zero-context "
            "successor, append PROGRESS.md, run `project-steward wrap "
            "--summary \"...\"`, and propose a git commit).",
        ))


def _stop_guard_state(root):
    return runtime_dir(root) / "stop_guard.json"


def _handle_stop(root, agent, payload):
    if not is_steward_project(root):
        return
    if payload.get("stop_hook_active"):
        return  # loop guard: this turn was already continued by a Stop hook
    config = load_config(root).get("session", {})
    mode = str(config.get("auto_handoff_mode", "block")).lower()
    if mode == "off":
        return
    min_edits = int(config.get("auto_handoff_min_edits", 5))
    cooldown_s = int(config.get("auto_handoff_cooldown_min", 45)) * 60

    _meta, _body, handoff_mtime = sessions.handoff_meta(root)
    edits = sessions.handoff_relevant_activity_count_since(root, handoff_mtime)
    if edits < min_edits:
        return

    guard = read_json(_stop_guard_state(root), {})
    last_auto = float(guard.get("last_auto_epoch", 0))
    if time.time() - last_auto < cooldown_s:
        return

    write_json_atomic(_stop_guard_state(root), {
        "last_auto_epoch": time.time(),
        "last_auto_at": utcnow_iso(),
    })
    sessions.log_event(root, "stop-guard", "mode=%s edits=%d" % (mode, edits))

    if mode == "remind":
        _emit({
            "systemMessage": (
                "Project Steward: %d handoff-relevant actions since "
                "HANDOFF.md was last updated. If project state changed "
                "materially, refresh HANDOFF.md; otherwise consider "
                "`project-steward checkpoint --note ...` for a lightweight "
                "checkpoint." % edits
            )
        })
        return

    # mode == "block": force one auto-checkpoint before stopping.
    _emit({
        "decision": "block",
        "reason": (
            "Project Steward auto-checkpoint: %d handoff-relevant actions have "
            "occurred since .project-steward/HANDOFF.md was last updated. "
            "Before finishing: if project state changed materially, update "
            "HANDOFF.md (Now / In flight / Next steps / Blockers) and append "
            "a one-line PROGRESS.md entry prefixed with [auto-checkpoint]. "
            "Otherwise run `project-steward checkpoint --note \"...\"` for a "
            "lightweight checkpoint; it refreshes checkpoint metadata and "
            "appends PROGRESS.md. Then stop. Keep it brief; do not start new "
            "work." % edits
        ),
    })


def _handle_pre_compact(root, agent, payload):
    if not is_steward_project(root):
        return
    sessions.write_snapshot(root, "pre-compact")


def _handle_session_end(root, agent, payload):
    if not is_steward_project(root):
        return
    sessions.write_snapshot(root, "session-end")
    sessions.close_runtime_session(root, "ended")


HANDLERS = {
    "session-start": _handle_session_start,
    "post-tool-use": _handle_post_tool_use,
    "user-prompt-submit": _handle_user_prompt_submit,
    "stop": _handle_stop,
    "pre-compact": _handle_pre_compact,
    "post-compact": _handle_pre_compact,   # same snapshot behavior
    "session-end": _handle_session_end,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    event = argv[0] if argv else ""
    agent = "unknown"
    if "--agent" in argv:
        idx = argv.index("--agent")
        if idx + 1 < len(argv):
            agent = argv[idx + 1]
    try:
        payload = _read_stdin_json()
        cwd = payload.get("cwd")
        root = find_project_root(cwd if isinstance(cwd, str) and cwd else None)
        handler = HANDLERS.get(event)
        if handler is not None:
            handler(root, agent, payload)
    except Exception:
        # Hooks must never break the agent loop.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
