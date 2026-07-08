"""Durable state (state.json, backend.json, config.toml) and Markdown
front matter helpers. Python 3.7+, stdlib only, atomic writes."""
from __future__ import annotations

import copy
import datetime
import json
import os
import tempfile
import time
from pathlib import Path

from . import __version__
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
    "init": {"run_project_scripts": False},
}


def utcnow_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def write_text_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".steward-tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
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


def load_config(root):
    """DEFAULT_CONFIG deep-merged with .project-steward/config.toml."""
    cfg_path = state_dir(root) / "config.toml"
    if not cfg_path.is_file():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        text = cfg_path.read_text(encoding="utf-8")
        return _deep_merge(DEFAULT_CONFIG, load_toml_text(text))
    except Exception:
        # Broken config must never break hooks; doctor reports it.
        return copy.deepcopy(DEFAULT_CONFIG)


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
    return read_json(state_dir(root) / "state.json", default_state())


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


def update_front_matter(path, updates):
    """Merge *updates* into the front matter of *path* (file must exist)."""
    path = Path(path)
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    meta.update(updates)
    write_text_atomic(path, render_front_matter(meta, body))
    return meta
