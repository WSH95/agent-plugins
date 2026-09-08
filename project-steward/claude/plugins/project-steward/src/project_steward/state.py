"""Durable state (state.json, backend.json, config.toml) and Markdown
front matter helpers. Python 3.7+, stdlib only, atomic writes."""
from __future__ import annotations

import copy
import datetime
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from . import StewardError, __version__
from .paths import state_dir
from .tomlmini import load_toml_text

DEFAULT_CONFIG = {
    "session": {
        # auto_handoff_mode: "block" | "remind" | "off"
        "auto_handoff_mode": "block",
        "auto_handoff_cooldown_min": 45,
        "auto_handoff_min_edits": 5,
    },
    "git": {
        # commit_policy: "ask" | "auto" | "never"
        "commit_policy": "ask",
        "never_push": True,
    },
    "backend": {"name": "markdown"},
    "init": {"run_project_scripts": False, "codex_hooks": True},
}


def utcnow_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def detect_newline(path, default="\n"):
    """The file's own line ending, taken from its first terminated line.

    Read from raw bytes: text mode would have translated it away.
    """
    try:
        with open(str(path), "rb") as fh:
            chunk = fh.read(8192)
    except OSError:
        return default
    index = chunk.find(b"\n")
    if index == -1:
        return default
    return "\r\n" if index and chunk[index - 1:index] == b"\r" else "\n"


def write_text_atomic(path, text, newline="\n"):
    """Atomically replace *path*.

    ``text`` must use LF internally; ``newline`` is what lands on disk, so
    callers can preserve a CRLF file's convention. A symlinked destination
    is written THROUGH — os.replace would otherwise swap the link itself
    for a regular file and sever it.
    """
    path = Path(path)
    if path.is_symlink():
        path = Path(os.path.realpath(str(path)))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".steward-tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        # os.replace transfers the temp file's inode, so the destination
        # would inherit mkstemp's owner-only 0600. Carry the existing mode
        # across, and give new files the usual 0644 instead of 0600.
        # Windows has no POSIX modes worth copying here.
        if os.name != "nt":
            try:
                if path.exists():
                    shutil.copymode(str(path), tmp)
                else:
                    os.chmod(tmp, 0o644)
            except OSError:
                pass
        for attempt in range(3):
            try:
                os.replace(tmp, str(path))
                break
            except PermissionError:
                # Windows: destination briefly locked by an editor,
                # antivirus, or sync client.
                if attempt == 2:
                    raise
                time.sleep(0.1)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def read_json(path, default=None):
    try:
        with open(str(path), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return copy.deepcopy(default)


def write_json_atomic(path, obj):
    write_text_atomic(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _deep_merge(base, extra):
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _config_problem(path, requirement, fallback):
    return "%s %s; using %s" % (path, requirement, fallback)


def _normalize_config(parsed):
    """Return a safe effective config and semantic diagnostics."""
    if not isinstance(parsed, dict):
        return copy.deepcopy(DEFAULT_CONFIG), [
            "config root must be a table; using defaults"
        ]

    config = _deep_merge(DEFAULT_CONFIG, parsed)
    problems = []
    for section in ("session", "git", "backend", "init"):
        if not isinstance(parsed.get(section, {}), dict):
            config[section] = copy.deepcopy(DEFAULT_CONFIG[section])
            problems.append(
                "%s section must be a table; using defaults" % section
            )

    session = config["session"]
    if session.get("auto_handoff_mode") not in ("block", "remind", "off"):
        session["auto_handoff_mode"] = "block"
        problems.append(_config_problem(
            "session.auto_handoff_mode",
            "must be block, remind, or off",
            "block",
        ))
    for key in ("auto_handoff_cooldown_min", "auto_handoff_min_edits"):
        value = session.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            fallback = DEFAULT_CONFIG["session"][key]
            session[key] = fallback
            problems.append(_config_problem(
                "session.%s" % key,
                "must be a nonnegative integer",
                str(fallback),
            ))

    git = config["git"]
    if git.get("commit_policy") not in ("auto", "ask", "never"):
        git["commit_policy"] = "ask"
        problems.append(_config_problem(
            "git.commit_policy", "must be auto, ask, or never", "ask"
        ))
    if not isinstance(git.get("never_push"), bool):
        git["never_push"] = DEFAULT_CONFIG["git"]["never_push"]
        problems.append(_config_problem(
            "git.never_push", "must be a boolean", "true"
        ))

    backend = config["backend"]
    if not isinstance(backend.get("name"), str):
        backend["name"] = DEFAULT_CONFIG["backend"]["name"]
        problems.append(_config_problem(
            "backend.name", "must be a string", "markdown"
        ))

    init = config["init"]
    for key, fallback in DEFAULT_CONFIG["init"].items():
        if not isinstance(init.get(key), bool):
            init[key] = fallback
            problems.append(_config_problem(
                "init.%s" % key,
                "must be a boolean",
                "true" if fallback else "false",
            ))
    return config, problems


def load_config_with_diagnostics(root):
    """Return normalized effective config plus parse/validation problems."""
    cfg_path = state_dir(root) / "config.toml"
    if not cfg_path.is_file():
        config, problems = _normalize_config({})
    else:
        try:
            text = cfg_path.read_text(encoding="utf-8")
            config, problems = _normalize_config(load_toml_text(text))
        except Exception as exc:
            config = copy.deepcopy(DEFAULT_CONFIG)
            problems = [str(exc)]

    active_backend = load_backend(root)
    backend_name = active_backend.get("name", "markdown") \
        if isinstance(active_backend, dict) else "markdown"
    if not isinstance(backend_name, str) or not backend_name:
        backend_name = "markdown"
    config["backend"]["name"] = backend_name
    return config, problems


def load_config(root):
    """Return normalized effective Project Steward configuration."""
    return load_config_with_diagnostics(root)[0]


def default_state(project_name=""):
    return {
        "schema_version": 1,
        "steward_version": __version__,
        "project_name": project_name,
        "created_at": utcnow_iso(),
        "last_wrap_at": None,
        "last_checkpoint_at": None,
    }


def load_state(root):
    """Durable project state. Never silently replaces an unreadable file."""
    path = state_dir(root) / "state.json"
    if not path.exists():
        return default_state()
    data = read_json(path, None)
    if not isinstance(data, dict):
        raise StewardError(
            "%s exists but is not valid JSON. Refusing to overwrite it — "
            "created_at and project_name would be lost. Fix or remove the "
            "file, then retry (`project-steward doctor` reports the same "
            "problem)." % path)
    return data


def save_state(root, state):
    write_json_atomic(state_dir(root) / "state.json", state)


def load_backend(root):
    return read_json(
        state_dir(root) / "backend.json",
        {"schema_version": 1, "name": "markdown", "adopted_at": None,
         "notes": "Built-in Markdown backend (PLAN.md owns tasks)."},
    )


def save_backend(root, backend):
    write_json_atomic(state_dir(root) / "backend.json", backend)


# --------------------------------------------------------------------------
# Markdown front matter (--- key: value --- block at top of file)
# --------------------------------------------------------------------------

def parse_front_matter(text):
    """Return (dict, body). Tolerates a missing front matter block."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta = {}
    for idx in range(1, len(lines)):
        line = lines[idx]
        if line.strip() == "---":
            body = "\n".join(lines[idx + 1:])
            if text.endswith("\n") and not body.endswith("\n"):
                body += "\n"
            return meta, body
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return {}, text  # never closed; treat as body


def render_front_matter(meta, body):
    lines = ["---"]
    for key, value in meta.items():
        lines.append("%s: %s" % (key, "" if value is None else value))
    lines.append("---")
    out = "\n".join(lines) + "\n" + body.lstrip("\n")
    if not out.endswith("\n"):
        out += "\n"
    return out


def update_front_matter(path, updates, remove_keys=()):
    """Merge updates and remove obsolete keys from Markdown front matter.

    Keeps the file's existing line endings: a one-line timestamp change must
    not rewrite every line of a CRLF checkout.
    """
    path = Path(path)
    newline = detect_newline(path)
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    meta.update(updates)
    for key in remove_keys:
        meta.pop(key, None)
    write_text_atomic(path, render_front_matter(meta, body), newline=newline)
    return meta
