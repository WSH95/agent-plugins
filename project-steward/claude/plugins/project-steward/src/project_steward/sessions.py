"""Session lifecycle: resume recap, crash detection, checkpoint, wrap.

Design rule (fixes a v0.1 Projectforge flaw): starting or resuming a session
must NOT dirty the git working tree. Active-session claims, heartbeats, and
activity logs live in `.project-steward/runtime/` (gitignored). Committed
files (HANDOFF.md, PROGRESS.md, ...) change only at semantic checkpoints
and wrap-up.
"""
from __future__ import annotations

import calendar
import os
import socket
import time
from pathlib import Path

from . import gitutil
from .paths import runtime_dir, state_dir
from .state import (load_config, load_state, parse_front_matter, read_json,
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


# --------------------------------------------------------------------------
# Runtime (gitignored) session records
# --------------------------------------------------------------------------

def _session_file(root):
    return runtime_dir(root) / "session.json"


def load_runtime_session(root):
    return read_json(_session_file(root), {})


def claim_session(root, agent):
    runtime_dir(root, create=True)
    previous = load_runtime_session(root)
    record = {
        "status": "active",
        "agent": agent or "unknown",
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": utcnow_iso(),
        "updated_at": utcnow_iso(),
    }
    write_json_atomic(_session_file(root), record)
    return previous, record


def close_runtime_session(root, status="closed"):
    record = load_runtime_session(root)
    if record:
        record["status"] = status
        record["updated_at"] = utcnow_iso()
        write_json_atomic(_session_file(root), record)


def record_activity(root, tool, detail=""):
    """Heartbeat + rotating activity log. Called by PostToolUse hooks."""
    runtime_dir(root, create=True)
    record = load_runtime_session(root)
    if record.get("status") == "active":
        record["updated_at"] = utcnow_iso()
        write_json_atomic(_session_file(root), record)
    detail_text = (detail or "")[:200].replace("\n", " ")
    line = "%s\t%s\t%s\n" % (utcnow_iso(), tool, detail_text)
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
            gitutil.head_sha(root), len(dirty),
            "\n".join(dirty) or "(clean)",
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
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        ts = parts[0]
        try:
            lt = time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
        if calendar.timegm(lt) <= epoch:
            continue
        tool = parts[1]
        detail = parts[2] if len(parts) > 2 else ""
        entries.append((tool, detail))
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


def activity_is_handoff_relevant(tool, detail=""):
    """Return True for activity that should pressure a handoff update."""
    tool_name = (tool or "").strip().lower()
    detail_text = detail or ""
    if STEWARD_STATE_MARKER in detail_text.replace("\\", "/"):
        return False
    if tool_name in MUTATING_TOOLS:
        return True
    if tool_name != "bash":
        return False
    command = _strip_env_assignments(_normalized_command(detail_text))
    if not command:
        return False
    if command in READ_ONLY_COMMAND_EXACT:
        return False
    for prefix in READ_ONLY_COMMAND_PREFIXES:
        if command == prefix.rstrip() or command.startswith(prefix):
            return False
    return True


def handoff_relevant_activity_count_since(root, epoch):
    return sum(
        1 for tool, detail in _activity_entries_newer_than(root, epoch)
        if activity_is_handoff_relevant(tool, detail)
    )


def handoff_meta(root):
    path = state_dir(root) / "HANDOFF.md"
    if not path.is_file():
        return {}, "", 0.0
    text = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return meta, body, mtime


def detect_crash_signals(root, runtime_record=None):
    """Independent signals that the previous session ended abnormally.

    Callers that have already claimed this session must pass the
    pre-claim record as ``runtime_record`` — otherwise the fresh claim
    itself reads as a crash marker.
    """
    signals = []
    meta, body, handoff_mtime = handoff_meta(root)

    if meta.get("session_status") == "active":
        signals.append(
            "HANDOFF.md front matter says `session_status: active` — the "
            "previous session never wrapped."
        )

    runtime = (load_runtime_session(root) if runtime_record is None
               else runtime_record)
    if runtime.get("status") == "active":
        signals.append(
            "Local runtime marker shows an active session on this device "
            "(%s, %s) with no close event."
            % (runtime.get("agent", "?"), runtime.get("updated_at", "?"))
        )

    edits_after_handoff = handoff_relevant_activity_count_since(
        root, handoff_mtime)
    if edits_after_handoff > 0:
        signals.append(
            "%d tool actions were logged locally AFTER the last HANDOFF.md "
            "update." % edits_after_handoff
        )

    dirty = gitutil.dirty_files(root)
    if dirty:
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

    last_commit = meta.get("last_commit", "")
    if last_commit:
        newer = gitutil.commits_since(root, last_commit)
        if newer > 0:
            signals.append(
                "%d commit(s) exist after the one recorded in HANDOFF.md "
                "(%s)." % (newer, last_commit)
            )

    op = gitutil.in_progress_operation(root)
    if op:
        signals.append("A git %s is in progress." % op)

    return signals


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

    ``runtime_record`` is forwarded to ``detect_crash_signals`` (pass the
    pre-claim record after ``claim_session``).
    """
    meta, body, _ = handoff_meta(root)
    milestone, open_tasks = _plan_current(root)
    section = _extract_section(body, "## Next steps")
    recap = {
        "handoff": {
            "updated_at": meta.get("updated_at", "unknown"),
            "updated_by": meta.get("updated_by", "unknown"),
            "session_status": meta.get("session_status", "unknown"),
            "branch": meta.get("branch", ""),
            "last_commit": meta.get("last_commit", ""),
        },
        "git": {
            "is_repo": gitutil.is_repo(root),
            "branch": gitutil.current_branch(root),
            "head": gitutil.head_sha(root),
            "dirty_count": len(gitutil.dirty_files(root)),
            "in_progress": gitutil.in_progress_operation(root),
        },
        "current_milestone": milestone,
        "open_tasks": open_tasks,
        "latest_progress": _progress_head(root),
        "open_questions": _open_questions(root),
        "next_steps_excerpt": section[:600],
        "crash_signals": detect_crash_signals(root, runtime_record),
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
        lines.append(
            "Git: branch %s @ %s, %d dirty file(s)%s"
            % (git["branch"] or "(unborn)", git["head"] or "(no commits)",
               git["dirty_count"],
               ", %s IN PROGRESS" % git["in_progress"] if git["in_progress"] else "")
        )
    else:
        lines.append("Git: not a repository")
    if recap["current_milestone"]:
        lines.append(
            "Milestone: %s (%d open task(s) in PLAN.md)"
            % (recap["current_milestone"], recap["open_tasks"])
        )
    if recap["latest_progress"]:
        lines.append("Latest progress entry: %s" % recap["latest_progress"])
    if recap["open_questions"]:
        lines.append("Open questions: %d in QUESTIONS.md" % recap["open_questions"])
    if recap["next_steps_excerpt"]:
        lines.append("Next steps (from handoff):")
        for step in recap["next_steps_excerpt"].splitlines()[:6]:
            lines.append("  " + step)
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
    header = "### %s — %s\n" % (utcnow_iso(), agent or "agent")
    entry = header + ("%s%s\n" % (prefix, note.strip())) + "\n"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = "# Progress log\n\nNewest first.\n\n"
    marker = "\n### "
    idx = text.find(marker)
    if idx == -1:
        new_text = text.rstrip("\n") + "\n\n" + entry
    else:
        new_text = text[: idx + 1] + entry + text[idx + 1:]
    write_text_atomic(path, new_text)


def checkpoint(root, note, agent, auto=False):
    prefix = "[auto-checkpoint] " if auto else ""
    append_progress(root, note, agent, prefix=prefix)
    handoff_path = state_dir(root) / "HANDOFF.md"
    if handoff_path.is_file():
        update_front_matter(handoff_path, {
            "updated_at": utcnow_iso(),
            "updated_by": agent or "agent",
            "branch": gitutil.current_branch(root),
            "last_commit": gitutil.head_sha(root),
        })
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

    for dirty in gitutil.dirty_files(root):
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
            "last_commit": gitutil.head_sha(root),
        })
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
        })
    close_runtime_session(root, "closed")
    log_event(root, "close", "quick close without full wrap")
