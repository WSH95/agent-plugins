"""Project-root discovery and canonical paths. Python 3.7+, stdlib only."""
from __future__ import annotations

import os
from pathlib import Path

from . import LEGACY_DIR_NAME, STATE_DIR_NAME


def find_project_root(start=None):
    """Walk upward from *start* (default cwd) looking for a steward project.

    Priority: .project-steward > .projectforge (legacy) > .git.
    Returns the directory containing the first marker found, else *start*.
    """
    cur = Path(start or os.getcwd()).resolve()
    git_root = None
    for candidate in [cur] + list(cur.parents):
        if (candidate / STATE_DIR_NAME).is_dir():
            return candidate
        if (candidate / LEGACY_DIR_NAME).is_dir():
            return candidate
        if git_root is None and (candidate / ".git").exists():
            git_root = candidate
    return git_root or cur


def state_dir(root):
    return Path(root) / STATE_DIR_NAME


def legacy_dir(root):
    return Path(root) / LEGACY_DIR_NAME


def runtime_dir(root, create=False):
    d = state_dir(root) / "runtime"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def sessions_dir(root, create=False):
    d = state_dir(root) / "sessions"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def is_steward_project(root):
    return state_dir(root).is_dir()


def has_legacy_state(root):
    return legacy_dir(root).is_dir()


# Durable, committed state files.
DURABLE_FILES = [
    "PROJECT.md",
    "PLAN.md",
    "PROGRESS.md",
    "HANDOFF.md",
    "DECISIONS.md",
    "QUESTIONS.md",
    "RISKS.md",
    "VERIFY.md",
    "config.toml",
    "state.json",
    "backend.json",
]

# Entries maintained inside the managed .gitignore block.
GITIGNORE_ENTRIES = [
    ".project-steward/runtime/",
    ".project-steward/tmp/",
    ".project-steward/migration-backup-projectforge/",
]
