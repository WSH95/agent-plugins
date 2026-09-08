"""Thin, cross-platform git wrappers. Never push; never commit implicitly."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

# Read-only queries stay snappy; a commit may run pre-commit hooks (lint,
# format, tests), and killing git mid-commit can leave .git/index.lock.
GIT_TIMEOUT = 10
GIT_WRITE_TIMEOUT = 120

# Distinct from each other and from any real git exit code: a timeout is not
# "git is missing", and neither is a clean tree.
GIT_MISSING = 127
GIT_TIMED_OUT = 124


def run_git(args, cwd, timeout=GIT_TIMEOUT, strip_output=True):
    """Run git and return (returncode, stdout). Never raises on failure."""
    try:
        proc = subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        output = proc.stdout.decode("utf-8", "replace")
        if proc.returncode:
            output += proc.stderr.decode("utf-8", "replace")
        return proc.returncode, output.strip() if strip_output else output
    except subprocess.TimeoutExpired:
        return GIT_TIMED_OUT, ""
    except OSError:
        return GIT_MISSING, ""


def git_available(cwd="."):
    rc, _ = run_git(["--version"], cwd)
    return rc == 0


def is_repo(root):
    rc, out = run_git(["rev-parse", "--is-inside-work-tree"], root)
    return rc == 0 and out == "true"


def current_branch(root):
    """Branch name; empty string on an unborn branch or outside a repo."""
    rc, out = run_git(["branch", "--show-current"], root)
    return out if rc == 0 else ""


def head_sha(root, short=True):
    args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
    rc, out = run_git(args, root)
    return out if rc == 0 else ""


def _relative_path(root, path):
    root_path = os.path.abspath(str(root))
    root_real = os.path.realpath(root_path)
    candidate = str(path)
    if not os.path.isabs(candidate):
        candidate = os.path.join(root_path, candidate)
    candidate = os.path.abspath(candidate)

    def relative_to(base, target):
        try:
            common = os.path.commonpath([base, target])
        except (OSError, ValueError):
            return ""
        if os.path.normcase(common) != os.path.normcase(base):
            return ""
        return os.path.relpath(target, base)

    relative = relative_to(root_path, candidate)
    if not relative:
        relative = relative_to(root_real, candidate)
    if not relative:
        return ""
    try:
        parent_real = os.path.realpath(os.path.dirname(candidate))
        if not relative_to(root_real, parent_real):
            return ""
    except (OSError, ValueError):
        return ""
    return Path(relative).as_posix()


def last_commit_for_path(root, path, short=True):
    """Latest visible commit that changed *path*, or an empty string."""
    relative = _relative_path(root, path)
    if not relative:
        return ""
    fmt = "%h" if short else "%H"
    rc, out = run_git(["log", "-1", "--format=%s" % fmt, "--", relative],
                      root)
    return out if rc == 0 else ""


def path_is_dirty(root, path):
    """Whether *path* has tracked or untracked working-tree changes."""
    relative = _relative_path(root, path)
    if not relative:
        return False
    rc, out = run_git(["status", "--porcelain", "--", relative], root)
    return rc == 0 and bool(out.strip())


def dirty_files(root):
    """Porcelain status lines, or None when git could not answer.

    None is not "clean": callers must not report a clean tree because the
    query timed out or git is unavailable.
    """
    rc, out = run_git(["status", "--porcelain"], root)
    if rc != 0:
        return None
    return [line for line in out.splitlines() if line.strip()]


def recent_log(root, n=5):
    rc, out = run_git(["log", "--oneline", "-n", str(n)], root)
    if rc != 0 or not out:
        return []
    return out.splitlines()


def has_remote(root):
    rc, out = run_git(["remote"], root)
    return rc == 0 and bool(out.strip())


def remote_url(root):
    rc, out = run_git(["remote", "get-url", "origin"], root)
    return out if rc == 0 else ""


def commits_since(root, sha):
    if not sha:
        return -1
    rc, out = run_git(["rev-list", "--count", "%s..HEAD" % sha], root)
    if rc != 0:
        return -1
    try:
        return int(out)
    except ValueError:
        return -1


def last_commit_epoch(root):
    rc, out = run_git(["log", "-1", "--format=%ct"], root)
    if rc != 0:
        return 0
    try:
        return int(out)
    except ValueError:
        return 0


def in_progress_operation(root):
    """Name of an in-flight git operation (merge/rebase/cherry-pick), if any."""
    checks = [
        ("MERGE_HEAD", "merge"),
        ("REBASE_HEAD", "rebase"),
        ("rebase-merge", "rebase"),
        ("rebase-apply", "rebase"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("BISECT_LOG", "bisect"),
    ]
    for name, label in checks:
        rc, git_path = run_git(["rev-parse", "--git-path", name], root)
        if rc != 0:
            return ""
        path = Path(git_path)
        if not path.is_absolute():
            path = Path(root) / path
        if path.exists():
            return label
    return ""


def suggest_commit_command(root, message, extra_paths=None):
    """Return the commit command to PROPOSE to the user (never executed here).

    The agent is instructed to run this string, so every interpolated value
    is shell-quoted: a summary containing quotes or `;` must not become a
    second command.
    """
    paths = [".project-steward"]
    for p in extra_paths or []:
        if p not in paths:
            paths.append(p)
    quoted = " ".join(shlex.quote(str(p)) for p in paths)
    return "git add %s && git commit -m %s" % (quoted, shlex.quote(message))


def stage_and_commit(root, message, paths):
    """Explicitly requested commit of the given paths only. Never pushes."""
    relative = []
    for path in paths:
        name = _relative_path(root, path)
        if not name or name == ".":
            return 1, "Commit paths must name files or directories inside the repository."
        if name not in relative:
            relative.append(name)
    if not relative:
        return 1, "No commit paths selected."
    rc, prefix = run_git(["rev-parse", "--show-prefix"], root)
    if rc:
        return rc, prefix
    index_relative = [prefix + name for name in relative]
    rc, out = run_git(["diff", "--cached", "--name-only", "--no-renames", "-z"],
                      root, strip_output=False)
    if rc:
        return rc, out
    unrelated = [name for name in out.split("\0") if name and not any(
        name == selected or name.startswith(selected + "/")
        for selected in index_relative)]
    if unrelated:
        return 1, "Refusing to commit unrelated staged changes: %s" % ", ".join(unrelated)

    # Optional instruction files may not exist. Include tracked deletions.
    selected = []
    for name in relative:
        rc, tracked = run_git(["--literal-pathspecs", "ls-files", "--", name], root)
        if rc:
            return rc, tracked
        if os.path.lexists(str(Path(root) / name)) or tracked:
            selected.append(name)
    if not selected:
        return 1, "No existing or tracked commit paths selected."
    rc, out = run_git(["--literal-pathspecs", "add", "--"] + selected, root,
                      timeout=GIT_WRITE_TIMEOUT)
    if rc != 0:
        return rc, out
    return run_git(["--literal-pathspecs", "commit", "--only", "-m", message,
                    "--"] + selected, root, timeout=GIT_WRITE_TIMEOUT)
