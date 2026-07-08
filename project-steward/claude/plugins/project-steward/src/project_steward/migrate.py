"""Migration: legacy Projectforge (.projectforge/) -> Project Steward.

Approval-gated (prompt or --yes). Steps:
  1. Full backup copy to .project-steward/migration-backup-projectforge/
     (gitignored via the managed block).
  2. Move known state files into .project-steward/; journal/ becomes
     runtime/journal-legacy/ (ignored).
  3. Convert KEY=value config into config.toml; create state.json and
     backend.json.
  4. Convert PROJECTFORGE managed-block markers and wrap the legacy
     "Agent session protocol (Projectforge)" heading section into the new
     managed block in AGENTS.md. Product-name mentions are rewritten ONLY
     inside steward-generated files/blocks, never in user prose.
  5. Refresh the managed .gitignore block, remove the legacy directory,
     and append a PROGRESS.md entry.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .managed_blocks import (convert_legacy_markers, unified_diff,
                             upsert_block)
from .paths import legacy_dir, runtime_dir, state_dir
from .scaffold import gitignore_block, session_protocol_block
from .sessions import append_progress
from .state import (default_state, utcnow_iso, write_json_atomic,
                    write_text_atomic)

LEGACY_STATE_FILES = ["PROJECT.md", "PLAN.md", "PROGRESS.md", "HANDOFF.md",
                      "DECISIONS.md"]

CONFIG_KEY_MAP = {
    "AUTO_HANDOFF_MODE": ("session", "auto_handoff_mode", "str"),
    "AUTO_HANDOFF_COOLDOWN_MIN": ("session", "auto_handoff_cooldown_min", "int"),
    "AUTO_HANDOFF_MIN_EDITS": ("session", "auto_handoff_min_edits", "int"),
    "COMMIT_POLICY": ("git", "commit_policy", "str"),
}

LEGACY_HEADING_RE = re.compile(
    r"^##\s+Agent session protocol \(Projectforge\)\s*$", re.MULTILINE)


def parse_legacy_config(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def render_config_toml(legacy_values):
    sections = {}
    for legacy_key, (section, key, kind) in CONFIG_KEY_MAP.items():
        if legacy_key not in legacy_values:
            continue
        raw = legacy_values[legacy_key]
        value = raw
        if kind == "int":
            try:
                value = int(raw)
            except ValueError:
                continue
        sections.setdefault(section, {})[key] = value
    lines = ["# Project Steward config (migrated from Projectforge)", ""]
    for section in ("session", "git"):
        lines.append("[%s]" % section)
        for key, value in sections.get(section, {}).items():
            if isinstance(value, int):
                lines.append("%s = %d" % (key, value))
            else:
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
                lines.append('%s = "%s"' % (key, escaped))
        lines.append("")
    return "\n".join(lines)


def migrate_agents_md(root):
    """Convert legacy markers/heading in AGENTS.md. Returns diff text."""
    path = Path(root) / "AGENTS.md"
    if not path.is_file():
        return ""
    old = path.read_text(encoding="utf-8")
    new = convert_legacy_markers(old)
    if LEGACY_HEADING_RE.search(new):
        # Replace the legacy heading section with the new managed block.
        lines = new.splitlines(True)
        start = end = None
        for idx, line in enumerate(lines):
            if start is None and LEGACY_HEADING_RE.match(line.rstrip("\n")):
                start = idx
                continue
            if start is not None and line.startswith("## "):
                end = idx
                break
        if start is not None:
            end = end if end is not None else len(lines)
            new = "".join(lines[:start]) + "".join(lines[end:])
            new = upsert_block(new, "agent-session-protocol",
                               session_protocol_block())
    if new != old:
        write_text_atomic(path, new)
        return unified_diff(old, new, "AGENTS.md")
    return ""


def migrate(root, project_name=""):
    """Perform the migration. Caller is responsible for user approval.

    Returns a report dict: moved files, diffs, notes.
    """
    root = Path(root)
    legacy = legacy_dir(root)
    if not legacy.is_dir():
        return {"ok": False, "error": "No .projectforge/ directory found."}
    sdir = state_dir(root)
    sdir.mkdir(parents=True, exist_ok=True)
    report = {"ok": True, "moved": [], "notes": [], "agents_diff": ""}

    # 1. Backup (ignored by the managed .gitignore block).
    backup = sdir / "migration-backup-projectforge"
    if not backup.exists():
        shutil.copytree(str(legacy), str(backup))
        report["notes"].append("Backup written to %s" % backup)

    # 2. Move known files (only when the target does not already exist).
    for name in LEGACY_STATE_FILES:
        src = legacy / name
        dst = sdir / name
        if src.is_file() and not dst.exists():
            text = src.read_text(encoding="utf-8", errors="replace")
            text = convert_legacy_markers(text)
            text = text.replace(".projectforge/", ".project-steward/")
            write_text_atomic(dst, text)
            report["moved"].append(name)
    journal = legacy / "journal"
    if journal.is_dir():
        target = runtime_dir(root, create=True) / "journal-legacy"
        if not target.exists():
            shutil.copytree(str(journal), str(target))
            report["notes"].append("journal/ preserved at runtime/journal-legacy/")

    # 3. Config conversion + new machine state.
    legacy_config = legacy / "config"
    if legacy_config.is_file() and not (sdir / "config.toml").exists():
        values = parse_legacy_config(
            legacy_config.read_text(encoding="utf-8", errors="replace"))
        write_text_atomic(sdir / "config.toml", render_config_toml(values))
        report["moved"].append("config -> config.toml")
    if not (sdir / "state.json").exists():
        state = default_state(project_name)
        state["migrated_from"] = "projectforge"
        state["migrated_at"] = utcnow_iso()
        write_json_atomic(sdir / "state.json", state)
    if not (sdir / "backend.json").exists():
        write_json_atomic(sdir / "backend.json", {
            "schema_version": 1, "name": "markdown",
            "adopted_at": utcnow_iso(),
            "notes": "Defaulted at migration; run `project-steward backend "
                     "recommend` to revisit.",
        })

    # 4. AGENTS.md markers/heading.
    report["agents_diff"] = migrate_agents_md(root)

    # 5. .gitignore block refresh (replaces old .projectforge/journal entry).
    gi = root / ".gitignore"
    old = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    cleaned = "\n".join(
        line for line in old.splitlines()
        if ".projectforge" not in line
    )
    new = upsert_block(cleaned, "runtime-state", gitignore_block(),
                       style="hash")
    if new != old:
        write_text_atomic(gi, new)
        report["moved"].append(".gitignore (managed block)")

    # Remove the legacy directory (backup + git history preserve it).
    shutil.rmtree(str(legacy))
    report["notes"].append(".projectforge/ removed (backup kept).")

    append_progress(root,
                    "Migrated Projectforge state to Project Steward "
                    "(.projectforge/ -> .project-steward/). Backup at "
                    ".project-steward/migration-backup-projectforge/.",
                    agent="project-steward migrate")
    return report
