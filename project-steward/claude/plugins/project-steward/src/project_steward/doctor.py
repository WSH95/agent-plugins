"""`project-steward doctor [--self]`: validate project and repo health.

Each check returns (status, name, detail) with status in {ok, warn, fail}.
Exit code is 1 only when at least one check FAILS.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__, gitutil
from .managed_blocks import find_legacy_blocks, has_block
from .paths import (DURABLE_FILES, has_legacy_state, is_steward_project,
                    state_dir)
from .security import scan_text_for_secrets
from .sessions import handoff_meta
from .state import load_config, parse_front_matter, read_json
from .tomlmini import load_toml_text

OK, WARN, FAIL = "ok", "warn", "fail"


def _check(results, status, name, detail=""):
    results.append({"status": status, "name": name, "detail": detail})


def run_checks(root, self_mode=False):
    root = Path(root)
    results = []

    # Environment ----------------------------------------------------------
    _check(results, OK, "python",
           "%d.%d.%d" % sys.version_info[:3]
           + ("" if sys.version_info >= (3, 7) else " (<3.7 unsupported)"))
    if sys.version_info < (3, 7):
        results[-1]["status"] = FAIL
    _check(results,
           OK if gitutil.git_available(root) else FAIL,
           "git available", "" if gitutil.git_available(root) else
           "git not found on PATH")
    cli_on_path = bool(shutil.which("project-steward"))
    if os.name == "nt":
        cli_missing_msg = ("Claude plugin hooks can use the bundled "
                           "launcher when Python is available; install "
                           "with pipx/pip for CLI commands and Codex hooks")
    else:
        cli_missing_msg = ("Claude plugin hooks can use the bundled "
                           "launcher; install with pipx/pip for CLI "
                           "commands and Codex hooks")
    _check(results, OK if cli_on_path else WARN,
           "project-steward on PATH",
           "" if cli_on_path else cli_missing_msg)

    # Project state ---------------------------------------------------------
    if not is_steward_project(root):
        if has_legacy_state(root):
            _check(results, WARN, "legacy state",
                   ".projectforge/ found — run `project-steward migrate`")
        else:
            _check(results, WARN, "state dir",
                   ".project-steward/ not found — run `project-steward init`")
        return results

    sdir = state_dir(root)
    for name in DURABLE_FILES:
        path = sdir / name
        _check(results, OK if path.is_file() else WARN,
               "state file %s" % name,
               "" if path.is_file() else "missing")

    # Parseability
    for jname in ("state.json", "backend.json"):
        path = sdir / jname
        if path.is_file():
            data = read_json(path, None)
            _check(results, OK if isinstance(data, dict) else FAIL,
                   "%s parses" % jname,
                   "" if isinstance(data, dict) else "invalid JSON")
    cfg_path = sdir / "config.toml"
    if cfg_path.is_file():
        try:
            load_toml_text(cfg_path.read_text(encoding="utf-8"))
            _check(results, OK, "config.toml parses")
        except Exception as exc:
            _check(results, FAIL, "config.toml parses", str(exc))

    # Handoff front matter + staleness
    meta, _body, handoff_mtime = handoff_meta(root)
    if meta:
        _check(results, OK, "HANDOFF.md front matter",
               "status=%s updated=%s" % (meta.get("session_status", "?"),
                                         meta.get("updated_at", "?")))
        last_commit_epoch = gitutil.last_commit_epoch(root)
        if last_commit_epoch and handoff_mtime and \
                last_commit_epoch - handoff_mtime > 6 * 3600:
            _check(results, WARN, "handoff freshness",
                   "last commit is newer than HANDOFF.md by >6h — wrap or "
                   "checkpoint")
        else:
            _check(results, OK, "handoff freshness")
    else:
        _check(results, WARN, "HANDOFF.md front matter", "missing or empty")

    # Top-level instruction files
    agents_path = root / "AGENTS.md"
    if agents_path.is_file():
        text = agents_path.read_text(encoding="utf-8")
        _check(results,
               OK if has_block(text, "agent-session-protocol") else WARN,
               "AGENTS.md session-protocol block",
               "" if has_block(text, "agent-session-protocol") else
               "managed block missing — re-run init scaffolding")
        legacy = find_legacy_blocks(text)
        _check(results, OK if not legacy else WARN,
               "no legacy PROJECTFORGE blocks",
               "" if not legacy else "found: %s" % ", ".join(legacy))
        lines = text.count("\n") + 1
        _check(results, OK if lines <= 300 else WARN, "AGENTS.md size",
               "%d lines" % lines + ("" if lines <= 300 else " (>300 — trim)"))
    else:
        _check(results, WARN, "AGENTS.md", "missing")
    claude_path = root / "CLAUDE.md"
    if claude_path.is_file():
        has_import = "@AGENTS.md" in claude_path.read_text(encoding="utf-8")
        _check(results, OK if has_import else WARN,
               "CLAUDE.md imports @AGENTS.md",
               "" if has_import else "no @AGENTS.md import found")
    else:
        _check(results, WARN, "CLAUDE.md", "missing (Claude Code will not "
                                           "read AGENTS.md by itself)")

    # Gitignore for runtime state
    gi = root / ".gitignore"
    gi_text = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    ignored = ".project-steward/runtime/" in gi_text
    _check(results, OK if ignored else FAIL, "runtime state gitignored",
           "" if ignored else ".project-steward/runtime/ missing from "
                              ".gitignore — session claims would dirty git")

    # Secrets scan over committed steward files
    findings = []
    for name in DURABLE_FILES:
        path = sdir / name
        if path.is_file():
            try:
                findings += scan_text_for_secrets(
                    path.read_text(encoding="utf-8", errors="replace"),
                    origin=".project-steward/%s" % name)
            except OSError:
                pass
    hard = [f for f in findings if not f.get("placeholder")]
    _check(results, OK if not findings else (FAIL if hard else WARN),
           "no secrets in committed steward files",
           "" if not findings else "; ".join(
               "%s in %s%s" % (f["label"], f["origin"],
                               " (placeholder?)" if f.get("placeholder")
                               else "")
               for f in findings[:5]))

    if has_legacy_state(root):
        _check(results, WARN, "legacy state",
               ".projectforge/ still present — run `project-steward migrate`")

    if self_mode:
        results += _self_checks(root)
    return results


def _self_checks(root):
    """Extra checks when running inside the Project Steward repo itself."""
    results = []
    root = Path(root)
    _check(results, OK
           if (root / "plugin-src" / "src" / "project_steward").is_dir()
           else FAIL,
           "self: package source present")
    _check(results, OK if (root / "tests").is_dir() else WARN,
           "self: tests/ present")
    for manifest in ("plugin-src/metadata.json",):
        path = root / manifest
        if path.is_file():
            data = read_json(path, None)
            _check(results, OK if isinstance(data, dict) else FAIL,
                   "self: %s parses" % manifest)
        else:
            _check(results, WARN, "self: %s" % manifest, "missing")
    for hooks_file in ("plugin-src/claude/hooks/hooks.json",
                       "plugin-src/codex/hooks/hooks.json"):
        path = root / hooks_file
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                _check(results, OK, "self: %s parses" % hooks_file)
            except ValueError as exc:
                _check(results, FAIL, "self: %s parses" % hooks_file, str(exc))
                continue
            if hooks_file == "plugin-src/claude/hooks/hooks.json":
                name = "self: %s schema" % hooks_file
                allowed = ("type", "command", "timeout")
                wrapper_ref = "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd"
                problems = []
                handlers = []
                if not isinstance(data, dict) or \
                        not isinstance(data.get("hooks"), dict):
                    problems.append("root must be an object with `hooks`")
                else:
                    unexpected = sorted(
                        k for k in data if k not in ("description", "hooks"))
                    if unexpected:
                        problems.append("unexpected root key(s): %s"
                                        % ", ".join(unexpected))
                    for groups in data["hooks"].values():
                        for group in (groups if isinstance(groups, list)
                                      else []):
                            if isinstance(group, dict):
                                handlers += list(group.get("hooks") or [])
                for handler in handlers:
                    if not isinstance(handler, dict):
                        problems.append("hook entries must be objects")
                        continue
                    unknown = sorted(k for k in handler if k not in allowed)
                    if unknown:
                        problems.append(
                            "unsupported hook field(s): %s — Claude Code "
                            "has no per-OS command variants (ADR 0019)"
                            % ", ".join(unknown))
                    command = handler.get("command", "")
                    if wrapper_ref not in command:
                        problems.append(
                            "command must run the wrapper via %s"
                            % wrapper_ref)
                    elif not (path.parent / "run-hook.cmd").is_file():
                        problems.append("hooks/run-hook.cmd is missing")
                if problems:
                    _check(results, FAIL, name,
                           "; ".join(sorted(set(problems))))
                else:
                    _check(results, OK, name,
                           "handlers run hooks/run-hook.cmd")
            if hooks_file == "plugin-src/codex/hooks/hooks.json":
                name = "self: %s schema" % hooks_file
                if not isinstance(data, dict):
                    _check(results, FAIL, name, "root must be an object")
                else:
                    unexpected = sorted(k for k in data if k != "hooks")
                    if unexpected:
                        _check(results, FAIL, name,
                               "unexpected root key(s): %s"
                               % ", ".join(unexpected))
                    elif "hooks" not in data:
                        _check(results, FAIL, name,
                               "missing root key(s): hooks")
                    elif not isinstance(data["hooks"], dict):
                        _check(results, FAIL, name,
                               "hooks must be an object")
                    else:
                        _check(results, OK, name, "root keys: hooks")
        else:
            _check(results, WARN, "self: %s" % hooks_file, "missing")
    # Unresolved template placeholders in the repo's own generated state
    sdir = state_dir(root)
    unresolved = []
    for name in ("PROJECT.md", "PLAN.md", "HANDOFF.md"):
        path = sdir / name
        try:
            if "$project_name" in path.read_text(encoding="utf-8"):
                unresolved.append(name)
        except OSError:
            pass
    _check(results, OK if not unresolved else WARN,
           "self: no unresolved placeholders",
           "" if not unresolved else ", ".join(unresolved))
    stale_urls = []
    for rel in ("plugin-src/metadata.json",
                "pyproject.toml"):
        path = root / rel
        try:
            if "github.com/USER/" in path.read_text(encoding="utf-8"):
                stale_urls.append(rel)
        except OSError:
            pass
    _check(results, OK if not stale_urls else WARN,
           "self: repo URLs set",
           "" if not stale_urls else
           "placeholder github.com/USER/ in %s — replace before publishing"
           % ", ".join(stale_urls))
    from .paths import DURABLE_FILES
    from .scaffold import _templates_root
    troot = _templates_root()
    missing = []
    if troot is None or troot.parent.name != "project_steward":
        _check(results, FAIL, "self: templates ship inside the package",
               "resolved to %s" % (troot or "<none>"))
    else:
        for name in ("AGENTS.md.template", "CLAUDE.md.template"):
            if not (troot / name).is_file():
                missing.append(name)
        for name in DURABLE_FILES:
            if not (troot / "project-steward" / (name + ".template")).is_file():
                missing.append(name + ".template")
        _check(results, OK if not missing else FAIL,
               "self: templates ship inside the package",
               "%d template(s)" % (len(DURABLE_FILES) + 2) if not missing
               else "missing: %s" % ", ".join(missing))
    try:
        import project_steward  # noqa: F401
        _check(results, OK, "self: package imports",
               "version %s" % __version__)
    except Exception as exc:  # pragma: no cover
        _check(results, FAIL, "self: package imports", str(exc))
    return results


def format_results(results):
    icon = {OK: "[ok]  ", WARN: "[warn]", FAIL: "[FAIL]"}
    lines = []
    for r in results:
        line = "%s %s" % (icon[r["status"]], r["name"])
        if r["detail"]:
            line += " — %s" % r["detail"]
        lines.append(line)
    fails = sum(1 for r in results if r["status"] == FAIL)
    warns = sum(1 for r in results if r["status"] == WARN)
    lines.append("")
    lines.append("doctor: %d check(s), %d warning(s), %d failure(s)"
                 % (len(results), warns, fails))
    return "\n".join(lines), fails
