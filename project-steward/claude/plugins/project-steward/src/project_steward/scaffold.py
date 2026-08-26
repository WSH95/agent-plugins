"""Deterministic scaffolding for `project-steward init`.

Creates .project-steward/ state files, AGENTS.md managed blocks, the
CLAUDE.md adapter, and the managed .gitignore block. Existing user content
is never overwritten: state files are only created when absent, and
AGENTS.md / CLAUDE.md are modified strictly inside managed blocks (with a
diff for review).
"""
from __future__ import annotations

import string
from pathlib import Path

from . import __version__
from .managed_blocks import unified_diff, upsert_block
from .paths import DURABLE_FILES, GITIGNORE_ENTRIES, state_dir
from .state import (default_state, utcnow_iso, write_json_atomic,
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


def task_backend_block(mapping):
    name = mapping.get("backend_name", "markdown")
    if name == "markdown":
        detail = ("Use `.project-steward/PLAN.md` for detailed tasks "
                  "(built-in Markdown backend).")
    else:
        detail = ("%s owns the detailed task list. Keep only milestones and "
                  "a pointer in `.project-steward/PLAN.md`; do not copy tasks "
                  "between systems." % name)
    return "## Task backend\n\n%s\n" % detail


def session_protocol_block():
    return SESSION_PROTOCOL_TEXT


SESSION_PROTOCOL_TEXT = """\
## Project Steward workflow

- Start by reading `.project-steward/HANDOFF.md`. Run `project-steward resume`
  when available, then recap the current task, next step, blockers, open
  questions, git state, and any crash signals.
- At meaningful checkpoints, write plain, factual updates to the relevant
  files in `.project-steward/` or run `project-steward checkpoint --note "..."`.
- Before pausing or switching agents, leave `HANDOFF.md` ready for someone
  without this chat. Run `project-steward wrap --summary "..."` when available.
- Propose Conventional Commits that include `.project-steward/`. Never push,
  force-push, or rewrite published history without explicit approval.
- Treat `AGENTS.md` and `CLAUDE.md` as user-owned files. Change only
  `PROJECT-STEWARD` managed blocks, show the diff first, and record the
  approved change in `.project-steward/DECISIONS.md`.
"""


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
    mapping = build_mapping(answers)
    result = {}

    # 1. State files: create-if-absent only.
    for name in DURABLE_FILES:
        rel = ".project-steward/%s" % name
        target = root / rel
        if target.exists():
            result[rel] = ("skip", None, "")
            continue
        template = _require_template(name + ".template")
        text = render(template, mapping)
        result[rel] = ("create", text, "")

    # 2. AGENTS.md: create from template, or upsert managed blocks only.
    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        old = agents_path.read_text(encoding="utf-8")
        new = old
    else:
        template = _require_template("AGENTS.md.template")
        old, new = "", render(template, mapping)
    new = upsert_block(new, "commands", commands_block(mapping))
    new = upsert_block(new, "task-backend", task_backend_block(mapping))
    new = upsert_block(new, "agent-session-protocol", session_protocol_block())
    if new != old:
        action = "update" if agents_path.exists() else "create"
        result["AGENTS.md"] = (action, new, unified_diff(old, new, "AGENTS.md"))
    else:
        result["AGENTS.md"] = ("noop", None, "")

    # 3. CLAUDE.md adapter: create, or ensure the @AGENTS.md import exists.
    claude_path = root / "CLAUDE.md"
    if claude_path.exists():
        old = claude_path.read_text(encoding="utf-8")
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
    old = gi_path.read_text(encoding="utf-8") if gi_path.exists() else ""
    new = upsert_block(old, "runtime-state", gitignore_block(), style="hash")
    if new != old:
        action = "update" if gi_path.exists() else "create"
        result[".gitignore"] = (action, new,
                                unified_diff(old, new, ".gitignore"))
    else:
        result[".gitignore"] = ("noop", None, "")

    return result, mapping


def apply_plan(root, plan, mapping):
    """Write the planned files. state.json/backend.json get real content."""
    root = Path(root)
    state_dir(root).mkdir(parents=True, exist_ok=True)
    (state_dir(root) / "runtime").mkdir(parents=True, exist_ok=True)
    written = []
    for rel, (action, text, _diff) in sorted(plan.items()):
        if action in ("skip", "noop") or text is None:
            continue
        target = root / rel
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
