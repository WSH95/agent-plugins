"""Project-root discovery and canonical paths. Python 3.7+, stdlib only."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from . import STATE_DIR_NAME, StewardError


class UnsafePathError(StewardError):
    """A write target escapes the project root, or sits under a symlink."""


def assert_inside_root(root, path, label):
    """Refuse *path* unless it and every ancestor stay inside *root*.

    Rejects symlinked or non-directory ancestors, so a symlinked
    `.project-steward/` cannot redirect writes outside the project.
    """
    root = Path(root)
    path = Path(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise UnsafePathError("%s is outside the project root" % label)
    ancestor = root
    for part in relative.parts[:-1]:
        ancestor = ancestor / part
        try:
            mode = ancestor.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise UnsafePathError("cannot inspect %s (%s)" % (ancestor, exc))
        if stat.S_ISLNK(mode):
            raise UnsafePathError(
                "%s has a symlinked ancestor: %s" % (label, ancestor))
        if not stat.S_ISDIR(mode):
            raise UnsafePathError(
                "%s has a non-directory ancestor: %s" % (label, ancestor))
    return path


def find_project_root(start=None):
    """Walk upward from *start* (default cwd) looking for a steward project.

    At each directory, managed and legacy state take priority over its Git
    marker. A Git marker stops the search so state from an enclosing repository
    is never selected. Returns the nearest matching directory, else *start*.
    """
    cur = Path(start or os.getcwd()).resolve()
    for candidate in [cur] + list(cur.parents):
        if (candidate / STATE_DIR_NAME).is_dir():
            return candidate
        if (candidate / ".git").exists():
            return candidate
    return cur


def state_dir(root):
    return Path(root) / STATE_DIR_NAME


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


# Durable, committed state files.
DURABLE_FILES = [
    "WORKFLOW.md",
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
]
