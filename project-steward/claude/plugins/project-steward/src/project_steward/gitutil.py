"""Thin, cross-platform git wrappers. Never push; never commit implicitly."""
from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT = 10


def run_git(args, cwd, timeout=GIT_TIMEOUT):
    """Run git and return (returncode, stdout). Never raises on failure."""
    try:
        proc = subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


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


def dirty_files(root):
    rc, out = run_git(["status", "--porcelain"], root)
    if rc != 0 or not out:
        return []
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
    git_dir = Path(root) / ".git"
    if not git_dir.exists():
        return ""
    checks = [
        ("MERGE_HEAD", "merge"),
        ("REBASE_HEAD", "rebase"),
        ("rebase-merge", "rebase"),
        ("rebase-apply", "rebase"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("BISECT_LOG", "bisect"),
    ]
    for name, label in checks:
        if (git_dir / name).exists():
            return label
    return ""


def suggest_commit_command(root, message, extra_paths=None):
    """Return the commit command to PROPOSE to the user (never executed here)."""
    paths = [".project-steward"]
    for p in extra_paths or []:
        if p not in paths:
            paths.append(p)
    quoted = " ".join('"%s"' % p for p in paths)
    return "git add %s && git commit -m \"%s\"" % (quoted, message)


def stage_and_commit(root, message, paths):
    """Explicitly requested commit of the given paths only. Never pushes."""
    rc, out = run_git(["add", "--"] + list(paths), root)
    if rc != 0:
        return rc, out
    return run_git(["commit", "-m", message], root)
