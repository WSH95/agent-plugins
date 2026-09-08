"""Session lifecycle: resume recap, crash detection, checkpoint, wrap.

Design rule: starting or resuming a session
must NOT dirty the git working tree. Active-session claims, heartbeats, and
activity logs live in `.project-steward/runtime/` (gitignored). Committed
files (HANDOFF.md, PROGRESS.md, ...) change only at semantic checkpoints
and wrap-up.
"""
from __future__ import annotations

import calendar
import os
import re
import socket
import time
from pathlib import Path

from . import StewardError, gitutil
from .paths import runtime_dir, state_dir
from .state import (detect_newline, load_config, load_state,
                    parse_front_matter, read_json,
                    save_state, update_front_matter, utcnow_iso,
                    write_json_atomic, write_text_atomic)

ACTIVITY_ROTATE_AT = 4000
ACTIVITY_KEEP = 2000
MUTATING_TOOLS = {
    "edit",
    "write",
    "multiedit",
    "notebookedit",
    "apply_patch",
    "search_replace",
}
SHELL_TOOLS = {
    "bash",
    "exec_command",
    "run_terminal_command",
    "shell_command",
}
READ_ONLY_COMMAND_PREFIXES = (
    "cat ",
    "codex --version",
    "command -v ",
    "diff ",
    "find ",
    "git diff",
    "git log",
    "git branch --list",
    "git branch --show-current",
    "git branch -a",
    "git branch -r",
    "git remote -v",
    "git rev-parse",
    "git show",
    "git status",
    "grep ",
    "head ",
    "ls ",
    "pwd",
    "python3 -m compileall ",
    "python3 -m json.tool ",
    "python3 -m project_steward doctor",
    "python3 -m project_steward --version",
    "python3 -m pytest ",
    "project-steward doctor",
    "project-steward resume",
    "project-steward status",
    "project-steward --version",
    "pytest ",
    "rg ",
    "sed -n ",
    "tail ",
    "wc ",
    "which ",
)
READ_ONLY_COMMAND_EXACT = (
    "git branch",
    "git remote",
    "pwd",
)
STEWARD_STATE_MARKER = ".project-steward/"

REQUIRED_HANDOFF_SECTIONS = ["## Now", "## Next steps"]
RECOMMENDED_HANDOFF_SECTIONS = [
    "## In flight", "## Blockers", "## Key files", "## Tried and rejected",
    "## Warnings",
]

_UNSPECIFIED_SESSION_ID = object()


# --------------------------------------------------------------------------
# Runtime (gitignored) session records
# --------------------------------------------------------------------------

def _session_file(root):
    return runtime_dir(root) / "session.json"


def load_runtime_session(root):
    return read_json(_session_file(root), {})


def claim_session(root, agent, session_id=None, reuse_current=False):
    """Claim the single current marker without replacing its owner blindly.

    Hook starts reuse an active marker with the same session ID. CLI resume
    passes ``reuse_current=True`` so it can join an already active marker.
    """
    runtime_dir(root, create=True)
    previous = load_runtime_session(root)
    active = previous.get("status") == "active"
    same_hook_session = (
        session_id is not None
        and previous.get("session_id") == session_id
    )
    if active and (reuse_current or same_hook_session):
        record = dict(previous)
        record["updated_at"] = utcnow_iso()
        write_json_atomic(_session_file(root), record)
        return previous, record

    now = utcnow_iso()
    record = {
        "status": "active",
        "agent": agent or "unknown",
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": now,
        "updated_at": now,
    }
    if session_id is not None:
        record["session_id"] = session_id
    write_json_atomic(_session_file(root), record)
    return previous, record


def close_runtime_session(root, status="closed",
                          session_id=_UNSPECIFIED_SESSION_ID):
    """Close the current marker, optionally only for its hook session ID.

    Calls that omit ``session_id`` are deliberate project-level operations.
    Passing ``None`` ownership-checks a legacy ID-less hook session.
    """
    record = load_runtime_session(root)
    if not record:
        return False
    if (session_id is not _UNSPECIFIED_SESSION_ID
            and record.get("session_id") != session_id):
        return False
    record["status"] = status
    record["updated_at"] = utcnow_iso()
    write_json_atomic(_session_file(root), record)
    return True


def record_activity(root, tool, detail="", session_id=None):
    """Log PostToolUse activity and heartbeat only its owned marker."""
    runtime_dir(root, create=True)
    record = load_runtime_session(root)
    if (record.get("status") == "active"
            and record.get("session_id") == session_id):
        record["updated_at"] = utcnow_iso()
        write_json_atomic(_session_file(root), record)
    relevant = activity_is_handoff_relevant(tool, detail)
    detail_text = (detail or "")[:200].replace("\n", " ")
    line = "%s\tv2\t%d\t%s\t%s\n" % (
        utcnow_iso(), 1 if relevant else 0, tool, detail_text)
    log_path = runtime_dir(root) / "activity.log"
    try:
        with open(str(log_path), "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except OSError:
        return
    _rotate(log_path)


def _rotate(log_path):
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines(True)
    except OSError:
        return
    if len(lines) > ACTIVITY_ROTATE_AT:
        write_text_atomic(log_path, "".join(lines[-ACTIVITY_KEEP:]))


def log_event(root, event, detail=""):
    runtime_dir(root, create=True)
    line = "%s\t%s\t%s\n" % (utcnow_iso(), event, detail)
    try:
        with open(str(runtime_dir(root) / "events.log"), "a",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except OSError:
        pass


def write_snapshot(root, reason):
    """Forensic snapshot (runtime): git status + recent activity."""
    runtime_dir(root, create=True)
    dirty = gitutil.dirty_files(root)
    dirty_label = ("(git state unavailable)" if dirty is None
                   else "\n".join(dirty) or "(clean)")
    recent = gitutil.recent_log(root, 5)
    activity_tail = []
    try:
        activity_tail = (runtime_dir(root) / "activity.log").read_text(
            encoding="utf-8").splitlines()[-10:]
    except OSError:
        pass
    text = (
        "# Snapshot (%s)\n\ntaken_at: %s\nbranch: %s\nhead: %s\n\n"
        "## Dirty files (%d)\n%s\n\n## Recent commits\n%s\n\n"
        "## Recent activity\n%s\n"
        % (
            reason, utcnow_iso(), gitutil.current_branch(root),
            gitutil.head_sha(root), len(dirty or []),
            dirty_label,
            "\n".join(recent) or "(none)",
            "\n".join(activity_tail) or "(none)",
        )
    )
    write_text_atomic(runtime_dir(root) / "last_snapshot.md", text)
    log_event(root, "snapshot", reason)


# --------------------------------------------------------------------------
# Recap and crash detection
# --------------------------------------------------------------------------

def _activity_lines_newer_than(root, epoch):
    path = runtime_dir(root) / "activity.log"
    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            ts = line.split("\t", 1)[0]
            try:
                lt = time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                if calendar.timegm(lt) > epoch:
                    count += 1
            except ValueError:
                continue
    except OSError:
        return 0
    return count


def _activity_entries_newer_than(root, epoch):
    path = runtime_dir(root) / "activity.log"
    entries = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return entries
    for line in lines:
        parts = line.split("\t", 4)
        if (len(parts) == 5 and parts[1] == "v2"
                and parts[2] in ("0", "1")):
            ts, _version, relevant_text, tool, detail = parts
            relevant = relevant_text == "1"
        else:
            parts = line.split("\t", 2)
            if len(parts) < 2:
                continue
            ts = parts[0]
            tool = parts[1]
            detail = parts[2] if len(parts) > 2 else ""
            relevant = None
        try:
            lt = time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
        if calendar.timegm(lt) <= epoch:
            continue
        entries.append((tool, detail, relevant))
    return entries


def _normalized_command(detail):
    return " ".join((detail or "").strip().split()).lower()


def _strip_env_assignments(command):
    tokens = command.split()
    if tokens and tokens[0] == "env":
        tokens = tokens[1:]
    while tokens:
        name, sep, _value = tokens[0].partition("=")
        if not sep:
            break
        if not name.replace("_", "").isalnum():
            break
        tokens = tokens[1:]
    return " ".join(tokens)


# `2>&1` merges descriptors; it is not a write to a file.
_FD_DUP_RE = re.compile(r">&\d")


def _shell_segments(command):
    """Split raw shell text on unquoted control operators.

    Returns ``(segments, writes_to_file)``. Quoted operators are literal, so
    ``rg -n 'todo|fixme'`` stays one segment. Splitting happens on the RAW
    text because ``_normalized_command`` folds newlines into spaces.
    """
    text = command or ""
    segments = []
    current = []
    quote = ""
    escaped = False
    writes = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            current.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            current.append(char)
            escaped = True
            index += 1
            continue
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
            index += 1
            continue
        if char == ">":
            duplication = _FD_DUP_RE.match(text, index)
            if duplication:
                if current and current[-1].isdigit():
                    current.pop()
                index = duplication.end()
                continue
            writes = True
            index += 1
            continue
        if char == "<":
            index += 1          # input redirection reads; it does not write
            continue
        if char in "&|;\r\n":
            segments.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return [s for s in (seg.strip() for seg in segments) if s], writes


def _segment_is_read_only(segment):
    command = _strip_env_assignments(_normalized_command(segment))
    if not command:
        return True
    if command in READ_ONLY_COMMAND_EXACT:
        return True
    for prefix in READ_ONLY_COMMAND_PREFIXES:
        if command == prefix.rstrip() or command.startswith(prefix):
            return True
    return False


def activity_is_handoff_relevant(tool, detail=""):
    """Return True for activity that should pressure a handoff update.

    The read-only allowlist is consulted BEFORE any shell-operator
    heuristic, so `git status | head` stays read-only. Every segment of a
    pipeline or list must be allowlisted: `ls && rm -rf /` is not read-only
    just because its first command is.
    """
    tool_name = (tool or "").strip().lower()
    detail_text = detail or ""
    if STEWARD_STATE_MARKER in detail_text.replace("\\", "/"):
        return False
    if tool_name in MUTATING_TOOLS:
        return True
    if tool_name not in SHELL_TOOLS:
        return False
    segments, writes_to_file = _shell_segments(detail_text)
    if writes_to_file:
        return True
    if not segments:
        return False
    return not all(_segment_is_read_only(seg) for seg in segments)


def handoff_relevant_activity_count_since(root, epoch):
    count = 0
    for tool, detail, relevant in _activity_entries_newer_than(root, epoch):
        if relevant is None:
            relevant = activity_is_handoff_relevant(tool, detail)
        if relevant:
            count += 1
    return count


def handoff_meta(root):
    path = state_dir(root) / "HANDOFF.md"
    if not path.is_file():
        return {}, "", 0.0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable or non-UTF-8. Callers include the SessionStart and Stop
        # hooks, which must never raise; report it as absent instead.
        return {}, "", 0.0
    meta, body = parse_front_matter(text)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return meta, body, mtime


def _handoff_commit(root):
    return gitutil.last_commit_for_path(
        root, state_dir(root) / "HANDOFF.md")


def detect_crash_signals(root, runtime_record=None):
    """Independent signals that the previous session ended abnormally.

    ``runtime_record`` remains accepted for callers using the earlier API.
    Active runtime markers are advisory and are reported by ``build_recap``.
    """
    signals = []
    meta, body, handoff_mtime = handoff_meta(root)

    if meta.get("session_status") == "active":
        signals.append(
            "HANDOFF.md front matter says `session_status: active` — the "
            "previous session never wrapped."
        )

    edits_after_handoff = handoff_relevant_activity_count_since(
        root, handoff_mtime)
    if edits_after_handoff > 0:
        signals.append(
            "%d tool actions were logged locally AFTER the last HANDOFF.md "
            "update." % edits_after_handoff
        )

    dirty = gitutil.dirty_files(root)
    if dirty is None:
        signals.append(
            "Git could not report working-tree state (timed out or "
            "unavailable); dirty-file and commit signals are unchecked.")
    elif dirty:
        unmentioned = [
            d for d in dirty
            if d.split()[-1].split("/")[-1] not in body
            and ".project-steward" not in d
        ]
        if unmentioned:
            signals.append(
                "%d dirty file(s) are not mentioned in the handoff (e.g. %s)."
                % (len(unmentioned), unmentioned[0].strip())
            )

    handoff_path = state_dir(root) / "HANDOFF.md"
    handoff_commit = _handoff_commit(root)
    if handoff_commit and not gitutil.path_is_dirty(root, handoff_path):
        newer = gitutil.commits_since(root, handoff_commit)
        if newer > 0:
            signals.append(
                "%d commit(s) exist after the last committed HANDOFF.md "
                "revision (%s)." % (newer, handoff_commit)
            )

    op = gitutil.in_progress_operation(root)
    if op:
        signals.append("A git %s is in progress." % op)

    return signals


def _runtime_notes(runtime_record):
    if runtime_record.get("status") != "active":
        return []
    return [
        "Local runtime marker is active on this device (%s, %s); this is "
        "advisory and may represent the current, repeated, or overlapping "
        "hook session."
        % (runtime_record.get("agent", "?"),
           runtime_record.get("updated_at", "?"))
    ]


def _dirty_count(root):
    """Number of dirty files, or None when git could not answer."""
    dirty = gitutil.dirty_files(root)
    return None if dirty is None else len(dirty)


def _plan_current(root):
    path = state_dir(root) / "PLAN.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "", 0
    current = ""
    open_tasks = 0
    in_current = False
    for line in lines:
        if line.startswith("## "):
            if not current:
                current = line[3:].strip()
                in_current = True
            else:
                in_current = False
        elif in_current and line.strip().startswith("- [ ]"):
            open_tasks += 1
    return current, open_tasks


def _progress_head(root):
    path = state_dir(root) / "PROGRESS.md"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("### "):
                return line[4:].strip()
    except OSError:
        pass
    return ""


def _open_questions(root):
    path = state_dir(root) / "QUESTIONS.md"
    try:
        return sum(
            1 for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- [ ]")
        )
    except OSError:
        return 0


def build_recap(root, runtime_record=None):
    """Structured recap for session start. Read-only.

    Pass the pre-claim record after ``claim_session`` so its advisory runtime
    note describes what was present before the claim or reuse.
    """
    from .state import load_backend
    meta, body, _ = handoff_meta(root)
    milestone, open_tasks = _plan_current(root)
    section = _extract_section(body, "## Next steps")
    runtime = (load_runtime_session(root) if runtime_record is None
               else runtime_record)
    recap = {
        "handoff": {
            "updated_at": meta.get("updated_at", "unknown"),
            "updated_by": meta.get("updated_by", "unknown"),
            "session_status": meta.get("session_status", "unknown"),
            "branch": meta.get("branch", ""),
            "last_commit": _handoff_commit(root),
        },
        "git": {
            "is_repo": gitutil.is_repo(root),
            "branch": gitutil.current_branch(root),
            "head": gitutil.head_sha(root),
            "dirty_count": _dirty_count(root),
            "in_progress": gitutil.in_progress_operation(root),
        },
        "current_milestone": milestone,
        "open_tasks": open_tasks,
        "task_backend": load_backend(root)["name"],
        "latest_progress": _progress_head(root),
        "open_questions": _open_questions(root),
        "next_steps_excerpt": section[:600],
        "crash_signals": detect_crash_signals(root, runtime_record),
        "runtime_notes": _runtime_notes(runtime),
    }
    return recap


def _extract_section(body, heading):
    lines = body.splitlines()
    collected = []
    inside = False
    for line in lines:
        if line.strip() == heading:
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside:
            collected.append(line)
    return "\n".join(collected).strip()


def format_recap(recap):
    handoff = recap["handoff"]
    git = recap["git"]
    lines = ["Project Steward — session recap"]
    lines.append(
        "Last handoff: %s by %s (status: %s)"
        % (handoff["updated_at"], handoff["updated_by"],
           handoff["session_status"])
    )
    if git["is_repo"]:
        dirty_count = git["dirty_count"]
        dirty_label = ("dirty state unavailable" if dirty_count is None
                       else "%d dirty file(s)" % dirty_count)
        lines.append(
            "Git: branch %s @ %s, %s%s"
            % (git["branch"] or "(unborn)", git["head"] or "(no commits)",
               dirty_label,
               ", %s IN PROGRESS" % git["in_progress"] if git["in_progress"] else "")
        )
    else:
        lines.append("Git: not a repository")
    backend = recap.get("task_backend", "markdown")
    if backend != "markdown":
        lines.append("Task backend: %s (PLAN.md is a milestone overview)" % backend)
    if recap["current_milestone"] and backend == "markdown":
        lines.append(
            "Milestone: %s (%d open task(s) in PLAN.md)"
            % (recap["current_milestone"], recap["open_tasks"])
        )
    elif recap["current_milestone"]:
        lines.append("Milestone: %s" % recap["current_milestone"])
    if recap["latest_progress"]:
        lines.append("Latest progress entry: %s" % recap["latest_progress"])
    if recap["open_questions"]:
        lines.append("Open questions: %d in QUESTIONS.md" % recap["open_questions"])
    if recap["next_steps_excerpt"]:
        lines.append("Next steps (from handoff):")
        for step in recap["next_steps_excerpt"].splitlines()[:6]:
            lines.append("  " + step)
    for note in recap.get("runtime_notes", []):
        lines.append("Runtime note: " + note)
    if recap["crash_signals"]:
        lines.append("ABNORMAL TERMINATION SUSPECTED:")
        for signal in recap["crash_signals"]:
            lines.append("  ! " + signal)
        lines.append(
            "  -> Reconstruct from `git diff`, `git log`, and "
            ".project-steward/runtime/, and label inferences as (inferred)."
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Checkpoint / wrap / close
# --------------------------------------------------------------------------

def append_progress(root, note, agent, prefix=""):
    path = state_dir(root) / "PROGRESS.md"
    newline = detect_newline(path)
    header = "### %s — %s\n" % (utcnow_iso(), agent or "agent")
    entry = header + ("%s%s\n" % (prefix, note.strip())) + "\n"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = "# Progress log\n\nNewest first.\n\n"
    except OSError as exc:
        # The log exists but cannot be read. Writing the fresh template here
        # would silently destroy the whole history.
        raise StewardError(
            "cannot read %s (%s). Refusing to replace the progress log with "
            "a new one. Fix the file, then retry." % (path, exc))
    marker = "\n### "
    idx = text.find(marker)
    if idx == -1:
        new_text = text.rstrip("\n") + "\n\n" + entry
    else:
        new_text = text[: idx + 1] + entry + text[idx + 1:]
    write_text_atomic(path, new_text, newline=newline)


def checkpoint(root, note, agent, auto=False):
    prefix = "[auto-checkpoint] " if auto else ""
    append_progress(root, note, agent, prefix=prefix)
    handoff_path = state_dir(root) / "HANDOFF.md"
    if handoff_path.is_file():
        update_front_matter(handoff_path, {
            "updated_at": utcnow_iso(),
            "updated_by": agent or "agent",
            "branch": gitutil.current_branch(root),
        }, remove_keys=("last_commit",))
    state = load_state(root)
    state["last_checkpoint_at"] = utcnow_iso()
    save_state(root, state)
    log_event(root, "checkpoint", ("auto " if auto else "") + note[:120])


def wrap(root, summary, agent):
    """Finalize a session. Returns a report dict with any warnings."""
    warnings = []
    handoff_path = state_dir(root) / "HANDOFF.md"
    body = ""
    if handoff_path.is_file():
        _, body, _ = handoff_meta(root)
        for section in REQUIRED_HANDOFF_SECTIONS:
            if section not in body:
                warnings.append(
                    "HANDOFF.md is missing a required '%s' section — write "
                    "it for a zero-context successor before finishing."
                    % section
                )
        for section in RECOMMENDED_HANDOFF_SECTIONS:
            if section not in body:
                warnings.append(
                    "Consider adding a '%s' section to HANDOFF.md." % section
                )
    else:
        warnings.append(".project-steward/HANDOFF.md does not exist.")

    tracked_dirty = gitutil.dirty_files(root)
    if tracked_dirty is None:
        warnings.append(
            "Git could not report working-tree state; unmentioned dirty "
            "files were not checked.")
    for dirty in tracked_dirty or []:
        name = dirty.split()[-1].split("/")[-1]
        if name and name not in body and ".project-steward" not in dirty:
            warnings.append(
                "Dirty file not mentioned in the handoff: %s" % dirty.strip()
            )

    if handoff_path.is_file():
        update_front_matter(handoff_path, {
            "updated_at": utcnow_iso(),
            "updated_by": agent or "agent",
            "session_status": "closed",
            "branch": gitutil.current_branch(root),
        }, remove_keys=("last_commit",))
    append_progress(root, summary or "Session wrapped.", agent)
    close_runtime_session(root, "closed")
    state = load_state(root)
    state["last_wrap_at"] = utcnow_iso()
    save_state(root, state)
    log_event(root, "wrap", summary[:120] if summary else "")

    config = load_config(root)
    policy = config.get("git", {}).get("commit_policy", "ask")
    suggestion = ""
    if gitutil.is_repo(root) and policy != "never":
        suggestion = gitutil.suggest_commit_command(
            root, "chore(steward): wrap session — %s" % (summary or "handoff")[:60],
        )
    return {"warnings": warnings, "commit_policy": policy,
            "commit_suggestion": suggestion}


def close_only(root, agent):
    """Quick close: mark status closed without a full handoff rewrite."""
    handoff_path = state_dir(root) / "HANDOFF.md"
    if handoff_path.is_file():
        update_front_matter(handoff_path, {
            "updated_at": utcnow_iso(),
            "updated_by": agent or "agent",
            "session_status": "closed",
        }, remove_keys=("last_commit",))
    close_runtime_session(root, "closed")
    log_event(root, "close", "quick close without full wrap")
