"""Read-only repository survey for interactive init.

Safe-init contract: this module only READS files. It never executes project
scripts, package-manager hooks, or network commands (see
references/security-model.md).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import gitutil

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".tox", ".idea",
    ".vscode", "target", ".next", ".cache",
}
MAX_FILES = 4000

LANG_BY_EXT = {
    ".py": "Python", ".ipynb": "Python (notebooks)", ".rs": "Rust",
    ".go": "Go", ".c": "C", ".h": "C/C++", ".cc": "C++", ".cpp": "C++",
    ".hpp": "C++", ".cu": "CUDA", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".swift": "Swift", ".m": "MATLAB/Obj-C", ".jl": "Julia", ".sh": "Shell",
    ".ps1": "PowerShell", ".lua": "Lua", ".md": "Markdown", ".tex": "LaTeX",
}

MANIFESTS = [
    "package.json", "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "environment.yml", "Pipfile", "poetry.lock",
    "Cargo.toml", "go.mod", "CMakeLists.txt", "Makefile", "pom.xml",
    "build.gradle", "Gemfile", "composer.json", "package.xml",  # ROS
]

AGENT_FILES = [
    "AGENTS.md", "CLAUDE.md", ".cursorrules",
    ".github/copilot-instructions.md", ".windsurfrules", "GEMINI.md",
]

TASK_SYSTEM_MARKERS = {
    "beads": [".beads"],
    "backlog_md": ["backlog"],
    "ccpm": [".claude/prds", ".claude/epics"],
    "taskmaster": [".taskmaster"],
    "spec_kit": [".specify", "specs"],
}

SENSITIVE_HINTS = [".env", ".env.local", "secrets", "credentials",
                   "id_rsa", ".pem", ".npmrc", ".pypirc"]


def _walk_language_counts(root):
    counts = {}
    seen = 0
    stack = [Path(root)]
    while stack and seen < MAX_FILES:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if seen >= MAX_FILES:
                break
            name = entry.name
            if entry.is_dir():
                if name not in SKIP_DIRS and not name.startswith(".git"):
                    stack.append(entry)
                continue
            seen += 1
            lang = LANG_BY_EXT.get(entry.suffix.lower())
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [{"language": k, "files": v} for k, v in ranked[:6]], seen


def _package_json_commands(root):
    path = Path(root) / "package.json"
    cmds = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {}) or {}
        for key in ("test", "build", "lint", "typecheck", "dev", "start"):
            if key in scripts:
                cmds[key] = "npm run %s" % key
    except (OSError, ValueError):
        pass
    return cmds


def _pyproject_commands(root):
    path = Path(root) / "pyproject.toml"
    cmds = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return cmds
    if "[tool.pytest" in text or (Path(root) / "tests").is_dir():
        cmds["test"] = "python -m pytest"
    if "[tool.ruff" in text:
        cmds["lint"] = "ruff check ."
    elif "[tool.flake8" in text:
        cmds["lint"] = "flake8"
    if "[tool.mypy" in text:
        cmds["typecheck"] = "mypy ."
    if "[build-system]" in text:
        cmds["build"] = "python -m build"
    return cmds


def _makefile_targets(root):
    path = Path(root) / "Makefile"
    targets = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"^([A-Za-z0-9_.-]+):(?!=)", line)
            if match and not match.group(1).startswith("."):
                targets.append(match.group(1))
    except OSError:
        return []
    return targets[:12]


def _candidate_commands(root):
    cmds = {}
    cmds.update(_pyproject_commands(root))
    for key, value in _package_json_commands(root).items():
        cmds.setdefault(key, value)
    if (Path(root) / "Cargo.toml").is_file():
        cmds.setdefault("test", "cargo test")
        cmds.setdefault("build", "cargo build")
        cmds.setdefault("lint", "cargo clippy")
    if (Path(root) / "go.mod").is_file():
        cmds.setdefault("test", "go test ./...")
        cmds.setdefault("build", "go build ./...")
    make_targets = _makefile_targets(root)
    for target in ("test", "build", "lint"):
        if target in make_targets:
            cmds.setdefault(target, "make %s" % target)
    return cmds, make_targets


def survey(root):
    """Gather facts. Returns a JSON-serializable dict of findings."""
    root = Path(root)
    exists = lambda rel: (root / rel).exists()  # noqa: E731

    languages, scanned = _walk_language_counts(root)
    commands, make_targets = _candidate_commands(root)

    ci_files = []
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        ci_files = sorted(p.name for p in workflows.glob("*.y*ml"))
    for extra in (".gitlab-ci.yml", "azure-pipelines.yml", ".circleci/config.yml"):
        if exists(extra):
            ci_files.append(extra)

    task_systems = {
        name: any(exists(marker) for marker in markers)
        for name, markers in TASK_SYSTEM_MARKERS.items()
    }

    git_info = {
        "is_repo": gitutil.is_repo(root),
        "branch": gitutil.current_branch(root),
        "head": gitutil.head_sha(root),
        "dirty_count": len(gitutil.dirty_files(root)),
        "has_remote": gitutil.has_remote(root),
        "remote_url": gitutil.remote_url(root),
        "recent_commits": gitutil.recent_log(root, 5),
        "in_progress": gitutil.in_progress_operation(root),
    }

    findings = {
        "root": str(root),
        "git": git_info,
        "docs": {
            "readme": exists("README.md") or exists("README.rst"),
            "contributing": exists("CONTRIBUTING.md"),
            "license": exists("LICENSE") or exists("LICENSE.md"),
            "docs_dir": exists("docs"),
            "changelog": exists("CHANGELOG.md"),
        },
        "manifests": [m for m in MANIFESTS if exists(m)],
        "ci": ci_files,
        "containers": {
            "dockerfile": exists("Dockerfile"),
            "compose": exists("docker-compose.yml") or exists("compose.yaml"),
        },
        "agent_files": [f for f in AGENT_FILES if exists(f)],
        "task_systems": task_systems,
        "languages": languages,
        "files_scanned": scanned,
        "candidate_commands": commands,
        "make_targets": make_targets,
        "sensitive_paths_present": [
            h for h in SENSITIVE_HINTS if exists(h)
        ],
        "empty_project": scanned == 0 and not git_info["is_repo"],
    }
    findings["open_questions"] = _open_questions(findings)
    return findings


def _open_questions(findings):
    """Load-bearing questions the survey could not answer."""
    questions = []
    cmds = findings["candidate_commands"]
    if not cmds.get("test"):
        questions.append("What command runs the test suite (if any)?")
    if not cmds.get("lint"):
        questions.append("Is there a lint/format command agents must run?")
    if not findings["docs"]["readme"]:
        questions.append("One-line project description (no README found)?")
    if len(findings["languages"]) > 1:
        questions.append("Which language/component is the primary focus?")
    if not findings["git"]["is_repo"]:
        questions.append("Initialize a git repository here? (recommended)")
    if findings["git"]["is_repo"] and not findings["git"]["has_remote"]:
        questions.append("Is there a remote to be aware of, or local-only?")
    active = [k for k, v in findings["task_systems"].items() if v]
    if active:
        questions.append(
            "Detected task system(s): %s — should it own fine-grained tasks?"
            % ", ".join(active)
        )
    return questions
