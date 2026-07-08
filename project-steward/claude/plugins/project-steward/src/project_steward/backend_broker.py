"""Backend broker: detect, score, recommend, and adopt task backends.

Principle: the user should not need to already know Backlog.md, beads,
CCPM, Taskmaster, Spec Kit, or GitHub Issues. The broker explains options
in plain English, never installs or switches anything silently, and
enforces single ownership of fine-grained tasks (an external backend owns
tasks -> PLAN.md becomes milestones + a pointer).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import gitutil
from .managed_blocks import unified_diff, upsert_block
from .paths import state_dir
from .scaffold import task_backend_block
from .state import load_backend, save_backend, utcnow_iso, write_text_atomic
from .sessions import _plan_current  # milestone/open-task counter

BACKENDS = {
    "markdown": {
        "display": "Built-in Markdown (PLAN.md)",
        "plain": "Zero dependencies. Tasks are checkboxes in "
                 ".project-steward/PLAN.md — readable anywhere, versioned "
                 "with git. Best for solo work and small task counts.",
        "repo": "",
        "install": "",
        "detect_paths": [],
        "detect_bins": [],
    },
    "backlog_md": {
        "display": "Backlog.md",
        "plain": "Git-native Markdown tasks with a Kanban board and CLI. A "
                 "step up from raw checkboxes without leaving Markdown.",
        "repo": "https://github.com/MrLesk/Backlog.md",
        "install": "npm i -g backlog.md   # verify against upstream README",
        "detect_paths": ["backlog"],
        "detect_bins": ["backlog"],
    },
    "beads": {
        "display": "beads (bd)",
        "plain": "A git-backed issue graph built for coding agents: "
                 "dependencies, blockers, ready-work queries (`bd ready`), "
                 "and atomic task claiming for multi-agent work.",
        "repo": "https://github.com/steveyegge/beads",
        "install": "See the beads README for the installer for your OS.",
        "detect_paths": [".beads"],
        "detect_bins": ["bd"],
    },
    "ccpm": {
        "display": "CCPM",
        "plain": "PRD -> epic -> tasks synced to GitHub Issues, with "
                 "parallel-agent worktrees. Best when GitHub Issues should "
                 "be the shared source of truth.",
        "repo": "https://github.com/automazeio/ccpm",
        "install": "Installed into .claude/ per the CCPM README.",
        "detect_paths": [".claude/prds", ".claude/epics"],
        "detect_bins": [],
    },
    "taskmaster": {
        "display": "Taskmaster",
        "plain": "Parses a PRD into a dependency-ordered task list and "
                 "tracks execution. Best for PRD-driven feature work.",
        "repo": "https://github.com/eyaltoledano/claude-task-master",
        "install": "npm i -g task-master-ai   # verify against upstream README",
        "detect_paths": [".taskmaster"],
        "detect_bins": ["task-master"],
    },
    "spec_kit": {
        "display": "GitHub Spec Kit",
        "plain": "Formal spec -> plan -> tasks workflow (specify CLI). Best "
                 "when you want written specs to gate implementation.",
        "repo": "https://github.com/github/spec-kit",
        "install": "uvx --from git+https://github.com/github/spec-kit.git "
                   "specify init   # verify against upstream README",
        "detect_paths": [".specify", "specs"],
        "detect_bins": ["specify"],
    },
    "github_issues": {
        "display": "GitHub Issues (via gh)",
        "plain": "Track tasks directly as GitHub Issues with the gh CLI. "
                 "Best when the team already lives in GitHub Issues.",
        "repo": "https://cli.github.com",
        "install": "Install the gh CLI and run `gh auth login`.",
        "detect_paths": [],
        "detect_bins": ["gh"],
    },
    # Explicit future/enterprise stubs (no adapter implemented):
    "linear": {"display": "Linear (stub)", "plain": "Not implemented; "
               "planned enterprise adapter.", "repo": "https://linear.app",
               "install": "", "detect_paths": [], "detect_bins": []},
    "jira": {"display": "Jira (stub)", "plain": "Not implemented; planned "
             "enterprise adapter.", "repo": "https://www.atlassian.com/software/jira",
             "install": "", "detect_paths": [], "detect_bins": []},
}

STUBS = {"linear", "jira"}

MIGRATION_THRESHOLDS = {
    "open_md_tasks": 25,
    "blockers": 5,
}


def detect(root):
    root = Path(root)
    found = {}
    for name, spec in BACKENDS.items():
        present_path = any((root / p).exists() for p in spec["detect_paths"])
        on_path = any(shutil.which(b) for b in spec["detect_bins"])
        found[name] = {
            "artifacts_in_repo": present_path,
            "tool_on_path": bool(on_path),
        }
    found["github_issues"]["github_remote"] = (
        "github.com" in gitutil.remote_url(root)
    )
    return found


def gather_signals(root):
    _milestone, open_tasks = _plan_current(root)
    blockers = _count_blockers(root)
    detected = detect(root)
    return {
        "open_md_tasks": open_tasks,
        "blockers": blockers,
        "has_remote": gitutil.has_remote(root),
        "github_remote": detected["github_issues"].get("github_remote", False),
        "prd_present": _prd_present(root),
        "detected": detected,
    }


def _count_blockers(root):
    path = state_dir(root) / "HANDOFF.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    count, inside = 0, False
    for line in lines:
        if line.strip().startswith("## "):
            inside = line.strip().lower().startswith("## blockers")
            continue
        if inside and line.strip().startswith(("-", "*")):
            count += 1
    return count


def _prd_present(root):
    root = Path(root)
    for pattern in ("PRD.md", "docs/PRD.md", "docs/prd.md"):
        if (root / pattern).is_file():
            return True
    docs = root / "docs"
    if docs.is_dir():
        try:
            return any("prd" in p.name.lower() for p in docs.iterdir())
        except OSError:
            return False
    return False


def score(root, signals=None):
    """Rule-based scores per references/backend-selection.md."""
    signals = signals or gather_signals(root)
    detected = signals["detected"]
    scores = {}

    def base(name):
        s = 0
        if detected[name]["artifacts_in_repo"]:
            s += 50  # already in use in this repo — strong signal
        if detected[name]["tool_on_path"]:
            s += 10
        return s

    scores["markdown"] = 20  # always viable
    if signals["open_md_tasks"] <= 10 and signals["blockers"] <= 2:
        scores["markdown"] += 15

    scores["backlog_md"] = base("backlog_md")
    if 10 < signals["open_md_tasks"] <= MIGRATION_THRESHOLDS["open_md_tasks"]:
        scores["backlog_md"] += 15

    scores["beads"] = base("beads")
    if signals["blockers"] >= 3:
        scores["beads"] += 20
    if signals["open_md_tasks"] > MIGRATION_THRESHOLDS["open_md_tasks"]:
        scores["beads"] += 15

    scores["ccpm"] = base("ccpm")
    if signals["github_remote"]:
        scores["ccpm"] += 10
    if signals["prd_present"] and signals["github_remote"]:
        scores["ccpm"] += 15

    scores["taskmaster"] = base("taskmaster")
    if signals["prd_present"]:
        scores["taskmaster"] += 15

    scores["spec_kit"] = base("spec_kit")
    if signals["prd_present"]:
        scores["spec_kit"] += 5

    scores["github_issues"] = base("github_issues")
    if signals["github_remote"]:
        scores["github_issues"] += 10

    for stub in STUBS:
        scores[stub] = 0
    return scores, signals


def recommend(root):
    scores, signals = score(root)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    entries = []
    for name, value in ranked:
        if name in STUBS:
            continue
        spec = BACKENDS[name]
        entries.append({
            "name": name,
            "display": spec["display"],
            "score": value,
            "plain": spec["plain"],
            "repo": spec["repo"],
            "install": spec["install"],
        })
    return {
        "signals": {k: v for k, v in signals.items() if k != "detected"},
        "detected": signals["detected"],
        "ranked": entries,
        "migration_hint": _migration_hint(signals),
    }


def _migration_hint(signals):
    hints = []
    if signals["open_md_tasks"] > MIGRATION_THRESHOLDS["open_md_tasks"]:
        hints.append(
            "PLAN.md has %d open tasks (> %d): consider a structured backend "
            "(beads or Backlog.md)."
            % (signals["open_md_tasks"], MIGRATION_THRESHOLDS["open_md_tasks"])
        )
    if signals["blockers"] >= MIGRATION_THRESHOLDS["blockers"]:
        hints.append(
            "%d blockers recorded: dependency-aware tracking (beads) would "
            "help." % signals["blockers"]
        )
    return " ".join(hints)


def adopt(root, name, assume_yes=False, confirm=None):
    """Adopt *name* as the task backend. Shows an AGENTS.md diff and asks
    for approval (unless assume_yes). Returns a report dict."""
    if name not in BACKENDS or name in STUBS:
        return {"ok": False, "error": "Unknown or stub backend: %s" % name}
    root = Path(root)
    agents_path = root / "AGENTS.md"
    old = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    new = upsert_block(old or "# Project\n", "task-backend",
                       task_backend_block({"backend_name": name}))
    diff = unified_diff(old, new, "AGENTS.md")
    if diff and not assume_yes:
        approved = confirm(diff) if confirm else False
        if not approved:
            return {"ok": False, "error": "Not approved; no changes written.",
                    "diff": diff}
    if new != old:
        write_text_atomic(agents_path, new)
    backend = load_backend(root)
    backend.update({"name": name, "adopted_at": utcnow_iso()})
    save_backend(root, backend)
    pointer_note = ""
    if name != "markdown":
        pointer_note = (
            "Reminder: %s now owns fine-grained tasks. Trim "
            ".project-steward/PLAN.md to milestones + a pointer (never two "
            "task lists)." % BACKENDS[name]["display"]
        )
    return {"ok": True, "backend": name, "diff": diff,
            "pointer_note": pointer_note,
            "install": BACKENDS[name]["install"],
            "repo": BACKENDS[name]["repo"]}
