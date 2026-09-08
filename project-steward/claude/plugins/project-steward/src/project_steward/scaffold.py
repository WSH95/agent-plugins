"""Deterministic scaffolding for `project-steward init`.

Creates .project-steward/ state files, AGENTS.md managed blocks, the
CLAUDE.md adapter, and the managed .gitignore block. Existing user content
is never overwritten: state files are only created when absent, and
AGENTS.md / CLAUDE.md are modified strictly inside managed blocks (with a
diff for review).
"""
from __future__ import annotations

import re
import string
from pathlib import Path

from . import __version__
from .managed_blocks import (get_block, has_block, remove_block, unified_diff,
                             upsert_block)
from .paths import assert_inside_root, DURABLE_FILES, GITIGNORE_ENTRIES, state_dir
from .state import (default_state, load_backend, load_config, utcnow_iso, write_json_atomic,
                    write_text_atomic)


class TemplateError(RuntimeError):
    """A required scaffold template is missing — the install is broken."""


def _templates_root():
    here = Path(__file__).resolve()
    # Templates ship inside the package; works for pip installs, the
    # plugin cache, and the repo checkout alike.
    packaged = here.parent / "templates"
    if packaged.is_dir():
        return packaged
    # Fallback for pre-0.2.3 layouts: <root>/templates next to src/.
    for base in [here.parent.parent.parent, here.parent.parent]:
        candidate = base / "templates"
        if candidate.is_dir():
            return candidate
    return None


def render(template_text, mapping):
    return string.Template(template_text).safe_substitute(mapping)


def _read_template(name):
    root = _templates_root()
    if root is None:
        return None
    for candidate in (root / name, root / "project-steward" / name):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return None


def _read_user_text(path):
    """Decode UTF-8 without universal-newline changes to user-owned bytes."""
    return Path(path).read_bytes().decode("utf-8")


def _require_template(name):
    text = _read_template(name)
    if text is None:
        raise TemplateError(
            "template %r not found (templates root: %s). The installed "
            "project-steward package is missing its templates/ data — "
            "reinstall from a complete source instead of proceeding with "
            "degraded state files." % (name, _templates_root() or "<none>"))
    return text


DEFAULT_ANSWERS = {
    "project_name": "Unnamed project",
    "one_liner": "TODO: one-line project description.",
    "primary_language": "unknown",
    "build_command": "TODO",
    "test_command": "TODO",
    "lint_command": "TODO",
    "backend_name": "markdown",
    "first_milestone": "M1: define the first milestone",
    "commit_policy": "auto",
    "created_at": "",
    "steward_version": __version__,
}


def build_mapping(answers=None):
    mapping = dict(DEFAULT_ANSWERS)
    mapping.update({k: v for k, v in (answers or {}).items() if v})
    if not mapping.get("created_at"):
        mapping["created_at"] = utcnow_iso()
    return mapping


# --------------------------------------------------------------------------
# Managed block contents (AGENTS.md, .gitignore)
# --------------------------------------------------------------------------

def commands_block(mapping):
    return (
        "## Commands\n\n"
        "- Build: `%(build_command)s`\n"
        "- Test: `%(test_command)s`\n"
        "- Lint: `%(lint_command)s`\n" % mapping
    )


COMMAND_FIELDS = (
    ("build_command", "Build"),
    ("test_command", "Test"),
    ("lint_command", "Lint"),
)


def update_commands_block(text, answers, mapping):
    """Update only command entries explicitly supplied during re-init."""
    body = get_block(text, "commands")
    if body is None:
        return upsert_block(text, "commands", commands_block(mapping))
    updated = body
    for key, label in COMMAND_FIELDS:
        value = answers.get(key)
        if not value:
            continue
        rendered = "`%s`" % value
        bullet = re.compile(
            r"^(?P<prefix>[ \t]*-[ \t]*%s:[ \t]*)`[^`\n]*`"
            r"(?P<suffix>[^\n]*)$" % re.escape(label),
            re.MULTILINE,
        )
        updated, count = bullet.subn(
            lambda match: match.group("prefix") + rendered
            + match.group("suffix"),
            updated,
            count=1,
        )
        if count:
            continue
        table = re.compile(
            r"^(?P<prefix>[ \t]*\|[ \t]*%s[ \t]*\|[ \t]*)"
            r"`[^`\n]*`(?P<suffix>[ \t]*\|[^\n]*)$" % re.escape(label),
            re.MULTILINE,
        )
        updated, count = table.subn(
            lambda match: match.group("prefix") + rendered
            + match.group("suffix"),
            updated,
            count=1,
        )
        if not count:
            updated = updated.rstrip("\n") + "\n- %s: %s" % (label, rendered)
    return upsert_block(text, "commands", updated)


def task_backend_block(mapping):
    name = mapping.get("backend_name", "markdown")
    if name == "markdown":
        detail = ("Use `.project-steward/PLAN.md` for detailed tasks "
                  "(built-in Markdown backend).")
    else:
        detail = ("%s owns detailed tasks and their status. Keep milestone "
                  "goals and a dated overview of active, blocked, next, and "
                  "recently completed work with task IDs in "
                  "`.project-steward/PLAN.md`. Update tasks in the backend "
                  "first, then refresh the overview and HANDOFF.md. If the "
                  "backend is unavailable, keep the last verified overview "
                  "and explain the limitation." % name)
    return "## Task backend\n\n%s\n" % detail


def session_protocol_block():
    return SESSION_PROTOCOL_TEXT


SESSION_PROTOCOL_TEXT = """\
## Project Steward workflow

Before starting work, read `.project-steward/WORKFLOW.md` and follow its
session, task-backend, and commit instructions.
"""


def workflow_text(mapping):
    text = render(_require_template("WORKFLOW.md.template"), mapping)
    return upsert_block(text, "task-backend", task_backend_block(mapping))


def gitignore_block():
    return "\n".join(GITIGNORE_ENTRIES)


# --------------------------------------------------------------------------
# Scaffolding
# --------------------------------------------------------------------------

def plan_files(root, answers=None):
    """Compute the scaffold as {relative_path: (action, new_text, diff)}.

    action is one of: create | update | skip (exists, state file) |
    noop (managed block already up to date).
    """
    root = Path(root)
    answers = dict(answers or {})
    warnings = []
    if state_dir(root).exists():
        backend_path = state_dir(root) / "backend.json"
        saved_backend = load_backend(root)
        saved_backend_name = saved_backend.get("name") \
            if isinstance(saved_backend, dict) else None
        if backend_path.is_file() and isinstance(saved_backend_name, str) \
                and saved_backend_name:
            requested_backend = answers.get("backend_name")
            if requested_backend and requested_backend != saved_backend_name:
                warnings.append(
                    "Existing backend.json keeps %s authoritative; ignored "
                    "requested backend %s. Use `project-steward backend adopt "
                    "%s` to switch consistently."
                    % (saved_backend_name, requested_backend,
                       requested_backend)
                )
            answers["backend_name"] = saved_backend_name
        elif not answers.get("backend_name"):
            answers["backend_name"] = saved_backend_name or "markdown"
        if not answers.get("commit_policy"):
            answers["commit_policy"] = "ask"
        if answers.get("codex_hooks") is None:
            init_config = load_config(root).get("init", {})
            if not isinstance(init_config, dict):
                init_config = {}
            answers["codex_hooks"] = init_config.get("codex_hooks", True)
    mapping = build_mapping(answers)
    if mapping["commit_policy"] not in ("auto", "ask", "never"):
        raise ValueError("commit_policy must be auto, ask, or never")
    mapping["codex_hooks"] = "false" if answers.get("codex_hooks") is False else "true"
    backend = mapping["backend_name"]
    if backend == "markdown":
        mapping["plan_intro"] = "Use this file for milestone goals and detailed tasks."
        mapping["milestone_work"] = "- [ ] Define the first concrete task."
    else:
        mapping["plan_intro"] = (
            "%s owns detailed tasks and their status. This overview is a "
            "summary; update task status in the backend first." % backend)
        mapping["milestone_work"] = (
            "Last reviewed: not yet verified against %s.\n\n"
            "| Work | Task IDs and summary |\n"
            "| --- | --- |\n"
            "| Active | Not yet assessed. |\n"
            "| Blocked | Not yet assessed. |\n"
            "| Next | Inspect the backend and select the first task. |\n"
            "| Recently completed | Not yet assessed. |" % backend)
    result = {}

    # 1. State files: create-if-absent only.
    for name in DURABLE_FILES:
        rel = ".project-steward/%s" % name
        target = root / rel
        if target.exists():
            result[rel] = ("skip", None, "")
            continue
        template = _require_template(name + ".template")
        text = (workflow_text(mapping) if name == "WORKFLOW.md"
                else render(template, mapping))
        result[rel] = ("create", text, "")

    # 2. AGENTS.md: create from template, or upsert managed blocks only.
    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        old = _read_user_text(agents_path)
        new = old
    else:
        template = _require_template("AGENTS.md.template")
        old, new = "", render(template, mapping)
    if not has_block(new, "commands"):
        new = upsert_block(new, "commands", commands_block(mapping))
    else:
        supplied_commands = [
            key for key, _label in COMMAND_FIELDS if answers.get(key)
        ]
        if len(supplied_commands) == len(COMMAND_FIELDS):
            new = upsert_block(new, "commands", commands_block(mapping))
        elif supplied_commands:
            new = update_commands_block(new, answers, mapping)
    new = remove_block(new, "task-backend")
    new = upsert_block(new, "agent-session-protocol", session_protocol_block())
    if new != old:
        action = "update" if agents_path.exists() else "create"
        result["AGENTS.md"] = (action, new, unified_diff(old, new, "AGENTS.md"))
    else:
        result["AGENTS.md"] = ("noop", None, "")

    # 3. CLAUDE.md adapter: create, or ensure the @AGENTS.md import exists.
    claude_path = root / "CLAUDE.md"
    if claude_path.exists():
        old = _read_user_text(claude_path)
        if "@AGENTS.md" in old:
            result["CLAUDE.md"] = ("noop", None, "")
        else:
            new = upsert_block(
                old, "import",
                "@AGENTS.md\n\n(Canonical instructions live in AGENTS.md; "
                "keep this file short and Claude-specific.)",
            )
            result["CLAUDE.md"] = ("update", new,
                                   unified_diff(old, new, "CLAUDE.md"))
    else:
        template = _require_template("CLAUDE.md.template")
        text = render(template, mapping)
        result["CLAUDE.md"] = ("create", text, "")

    # 4. .gitignore managed block for runtime state.
    gi_path = root / ".gitignore"
    old = _read_user_text(gi_path) if gi_path.exists() else ""
    new = upsert_block(old, "runtime-state", gitignore_block(), style="hash")
    if new != old:
        action = "update" if gi_path.exists() else "create"
        result[".gitignore"] = (action, new,
                                unified_diff(old, new, ".gitignore"))
    else:
        result[".gitignore"] = ("noop", None, "")

    from . import codex_setup
    codex_plan, codex_warnings = codex_setup.plan_files(
        root, enabled=answers.get("codex_hooks") is not False)
    result.update(codex_plan)
    warnings.extend(codex_warnings)
    mapping["_warnings"] = warnings
    return result, mapping


def apply_plan(root, plan, mapping):
    """Write the planned files. state.json/backend.json get real content."""
    root = Path(root)
    # A symlinked .project-steward/ would redirect every write out of the
    # project; refuse before creating anything.
    assert_inside_root(root, state_dir(root) / "runtime", ".project-steward/")
    state_dir(root).mkdir(parents=True, exist_ok=True)
    (state_dir(root) / "runtime").mkdir(parents=True, exist_ok=True)
    written = []
    for rel, (action, text, _diff) in sorted(plan.items()):
        if action in ("skip", "noop") or text is None:
            continue
        target = assert_inside_root(root, root / rel, rel)
        if rel == ".project-steward/state.json":
            state = default_state(mapping.get("project_name", ""))
            write_json_atomic(target, state)
        elif rel == ".project-steward/backend.json":
            write_json_atomic(target, {
                "schema_version": 1,
                "name": mapping.get("backend_name", "markdown"),
                "adopted_at": mapping["created_at"],
                "notes": "Set at init; run `project-steward backend "
                         "recommend` to revisit.",
            })
        else:
            write_text_atomic(target, text)
        written.append(rel)
    return written
