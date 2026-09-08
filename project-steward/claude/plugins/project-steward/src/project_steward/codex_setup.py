"""Plan safe project-local Codex hook setup."""
from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path

from .managed_blocks import unified_diff
from .tomlmini import TomlMiniError, loads as _tomlmini_loads

try:
    import tomllib as _tomllib
except ImportError:  # Python 3.7-3.10
    _tomllib = None


CONFIG_TEXT = "[features]\nhooks = true\n"
CONFIG_REL = ".codex/config.toml"
HOOKS_REL = ".codex/hooks.json"


def _template_text():
    path = Path(__file__).resolve().parent / "templates" / \
        "codex-hooks.json.template"
    return path.read_text(encoding="utf-8")


def _reject_json_constant(value):
    raise ValueError("invalid JSON constant %s" % value)


def _load_json(text):
    return json.loads(text, parse_constant=_reject_json_constant)


def _skip_entries():
    return {
        CONFIG_REL: ("skip", None, ""),
        HOOKS_REL: ("skip", None, ""),
    }


def _is_within(root, target):
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _strip_toml_comment(line):
    result = []
    quote = None
    escaped = False
    for char in line:
        if quote:
            result.append(char)
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
            result.append(char)
        elif char == "#":
            break
        else:
            result.append(char)
    return "".join(result).strip()


def _unquoted_index(text, needle):
    quote = None
    escaped = False
    for index, char in enumerate(text):
        if quote:
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == needle:
            return index
    return -1


def _contains_inline_hooks(config):
    return isinstance(config, dict) and "hooks" in config


def _validate_config(config_text):
    """Return (valid, detail, parsed); valid is None without a full parser."""
    if _tomllib is None:
        fallback_status = _narrow_toml_status(config_text)
        if fallback_status is True:
            try:
                return True, "", _tomlmini_loads(config_text)
            except TomlMiniError as exc:
                if "unsupported value" not in str(exc):
                    return (False,
                            "malformed .codex/config.toml: %s" % exc,
                            None)
        elif fallback_status is False:
            return False, (
                "malformed .codex/config.toml: outside the validated "
                "scalar/table TOML subset"
            ), None
        return None, (
            "cannot safely validate this richer Codex TOML with the Python "
            "3.7-3.10 standard library; use Python 3.11+ or merge hooks "
            "manually"
        ), None
    try:
        parsed = _tomllib.loads(config_text)
    except Exception as exc:
        return False, "malformed .codex/config.toml: %s" % exc, None
    return True, "", parsed


_SIMPLE_NUMBER = re.compile(
    r"^[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"
)
_ASCII_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _has_ambiguous_characters(text):
    return any(
        ord(char) == 127 or ord(char) < 32 or
        0xD800 <= ord(char) <= 0xDFFF
        for char in text
    )


def _narrow_scalar_status(value):
    if not value:
        return False
    if value[0] in ("'", '"'):
        quote = value[0]
        if "\\" in value or _has_ambiguous_characters(value[1:]):
            return None
        for index in range(1, len(value)):
            char = value[index]
            if char == quote:
                return not value[index + 1:].strip()
        return False
    if _has_ambiguous_characters(value):
        return None
    if value in ("true", "false") or _SIMPLE_NUMBER.match(value):
        return True
    if value.lower() in ("true", "false"):
        return False
    return None


def _narrow_toml_status(config_text):
    """Validate a narrow, unambiguous subset for older Python runtimes."""
    # Do not let strip()/splitlines() normalize invalid TOML into this subset.
    if any(ord(char) > 126 or (ord(char) < 32 and char not in "\t\r\n")
           for char in config_text) or "\r" in config_text.replace("\r\n", ""):
        return None
    if '"""' in config_text or "'''" in config_text:
        return None
    table = []
    assignments = set()
    tables = set()
    for raw_line in config_text.splitlines():
        line = _strip_toml_comment(raw_line)
        if not line:
            continue
        if line.startswith("[["):
            return None
        if line.startswith("["):
            if not line.endswith("]"):
                return False
            table_name = line[1:-1].strip()
            if not _ASCII_BARE_KEY.match(table_name):
                if ("." in table_name or "'" in table_name or
                        '"' in table_name or
                        any(ord(char) > 127 for char in table_name)):
                    return None
                return False
            table = [table_name]
            table_key = tuple(table)
            if table_key in tables or table_key in assignments:
                return False
            tables.add(table_key)
            continue
        equals = _unquoted_index(line, "=")
        if equals < 0:
            return False
        key = line[:equals].strip()
        if not _ASCII_BARE_KEY.match(key):
            if ("." in key or "'" in key or '"' in key or
                    any(ord(char) > 127 for char in key)):
                return None
            return False
        assignment = tuple(table + [key])
        if assignment in assignments or assignment in tables:
            return False
        assignments.add(assignment)
        scalar_status = _narrow_scalar_status(line[equals + 1:].strip())
        if scalar_status is not True:
            return scalar_status
    return True


def _validate_hooks(data):
    if not isinstance(data, dict):
        return "root must be an object"
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return "`hooks` must be an object"
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            return "hook event %r must be a list" % event
        for group in groups:
            if not isinstance(group, dict):
                return "hook groups for %r must be objects" % event
            handlers = group.get("hooks", [])
            if not isinstance(handlers, list):
                return "handlers for %r must be a list" % event
            if any(not isinstance(handler, dict) for handler in handlers):
                return "handlers for %r must be objects" % event
    return ""


def _normalized_command(handler):
    command = handler.get("command")
    if not isinstance(command, str):
        return ""
    return " ".join(command.split())


def _merge_hooks(existing, canonical):
    merged = copy.deepcopy(existing)
    hooks = merged.setdefault("hooks", {})
    for event, canonical_groups in canonical["hooks"].items():
        groups = hooks.setdefault(event, [])
        managed_commands = {
            _normalized_command(handler)
            for group in canonical_groups
            for handler in group.get("hooks", [])
            if _normalized_command(handler)
        }
        seen = set()
        for group in groups:
            handlers = group.get("hooks", [])
            filtered = []
            for handler in handlers:
                command = _normalized_command(handler)
                if command in managed_commands:
                    if command in seen:
                        continue
                    seen.add(command)
                filtered.append(handler)
            if filtered != handlers:
                group["hooks"] = filtered
        for canonical_group in canonical_groups:
            commands = {
                _normalized_command(handler)
                for handler in canonical_group.get("hooks", [])
                if _normalized_command(handler)
            }
            installed = {
                _normalized_command(handler)
                for group in groups
                for handler in group.get("hooks", [])
                if _normalized_command(handler)
            }
            if not commands.issubset(installed):
                groups.append(copy.deepcopy(canonical_group))
    return merged


def _feature_hooks_value(config):
    if not isinstance(config, dict):
        return None
    features = config.get("features")
    if not isinstance(features, dict):
        return None
    value = features.get("hooks")
    return value if isinstance(value, bool) else None


def _canonical_commands():
    canonical = _load_json(_template_text())
    return {
        event: {
            _normalized_command(handler)
            for group in groups
            for handler in group.get("hooks", [])
            if _normalized_command(handler)
        }
        for event, groups in canonical["hooks"].items()
    }


def _result(status, name, detail=""):
    return {"status": status, "name": name, "detail": detail}


def inspect_setup(root):
    """Return doctor-compatible checks for project-local Codex hooks."""
    root = Path(root)
    config_path = root / CONFIG_REL
    hooks_path = root / HOOKS_REL
    safe = all(_is_within(root, target) for target in (
        root / ".codex", config_path, hooks_path
    ))
    installed = False
    installation_detail = "missing .codex/hooks.json"
    if not safe:
        installation_detail = "Codex path resolves outside the project root"
    elif hooks_path.is_file():
        try:
            data = _load_json(hooks_path.read_text(encoding="utf-8"))
            problem = _validate_hooks(data)
        except (OSError, UnicodeError, ValueError) as exc:
            data = None
            problem = "malformed or unreadable JSON: %s" % exc
        if problem:
            installation_detail = problem
        else:
            missing = []
            for event, commands in _canonical_commands().items():
                installed_commands = {
                    _normalized_command(handler)
                    for group in data.get("hooks", {}).get(event, [])
                    for handler in group.get("hooks", [])
                    if _normalized_command(handler)
                }
                if not commands.issubset(installed_commands):
                    missing.append(event)
            if missing:
                installation_detail = (
                    "missing Project Steward event(s): %s"
                    % ", ".join(missing)
                )
            else:
                installed = True
                installation_detail = "4 Project Steward event handlers found"

    results = [_result(
        "ok" if installed else "warn",
        "Codex hooks installed",
        installation_detail,
    )]

    feature = None
    config_problem = ""
    config_status = None
    if safe and config_path.is_file():
        try:
            config_text = config_path.read_bytes().decode("utf-8")
            config_status, config_problem, parsed_config = _validate_config(
                config_text
            )
            if config_status:
                feature = _feature_hooks_value(parsed_config)
        except (OSError, UnicodeError) as exc:
            config_problem = "cannot read .codex/config.toml: %s" % exc
    if config_problem:
        activation_detail = config_problem
    elif feature is False:
        activation_detail = "hooks are disabled by .codex/config.toml"
    elif installed:
        activation_detail = (
            "feature is enabled%s; trust unknown — review in Codex /hooks"
            % (" by default" if feature is None else "")
        )
    else:
        activation_detail = "hook activation unavailable until installed"
    activation_status = "fail" if config_status is False else "warn"
    results.append(_result(activation_status, "Codex hooks activation",
                           activation_detail))

    cli = shutil.which("project-steward")
    results.append(_result(
        "ok" if cli else "warn",
        "Codex hook CLI on PATH",
        cli or "project-steward is missing from PATH; Codex hooks cannot run",
    ))
    return results


def plan_files(root, enabled=True):
    """Return Codex scaffold entries and non-fatal setup warnings."""
    if not enabled:
        return {}, []
    root = Path(root)
    config_path = root / CONFIG_REL
    hooks_path = root / HOOKS_REL
    codex_dir = root / ".codex"
    for target in (codex_dir, config_path, hooks_path):
        if not _is_within(root, target):
            return _skip_entries(), [
                "Codex setup skipped: %s resolves outside the project root."
                % target
            ]
    if codex_dir.exists() and not codex_dir.is_dir():
        return _skip_entries(), [
            "Codex setup skipped: .codex exists but is not a directory."
        ]

    config_exists = config_path.exists()
    if config_exists:
        try:
            config_text = config_path.read_bytes().decode("utf-8")
        except (OSError, UnicodeError) as exc:
            return _skip_entries(), [
                "Codex setup skipped: cannot read .codex/config.toml: %s"
                % exc
            ]
        valid_config, validation_detail, parsed_config = _validate_config(
            config_text
        )
        if valid_config is not True:
            return _skip_entries(), [
                "Codex setup skipped: %s." % validation_detail
            ]
        if _contains_inline_hooks(parsed_config):
            return _skip_entries(), [
                "Codex setup skipped: .codex/config.toml defines inline "
                "hooks; keep that configuration unchanged or merge "
                "Project Steward manually."
            ]

    canonical_text = _template_text()
    canonical = _load_json(canonical_text)
    if hooks_path.exists():
        try:
            old = hooks_path.read_text(encoding="utf-8")
            existing = _load_json(old)
        except (OSError, UnicodeError, ValueError) as exc:
            return _skip_entries(), [
                "Codex setup skipped: .codex/hooks.json is malformed or "
                "unreadable: %s" % exc
            ]
        problem = _validate_hooks(existing)
        if problem:
            return _skip_entries(), [
                "Codex setup skipped: .codex/hooks.json cannot be safely "
                "merged (%s)." % problem
            ]
        merged = _merge_hooks(existing, canonical)
        new = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
        hook_entry = (("noop", None, "") if merged == existing else (
            "update", new, unified_diff(old, new, HOOKS_REL)
        ))
    else:
        hook_entry = ("create", canonical_text, "")

    config_entry = (("skip", None, "") if config_exists else
                    ("create", CONFIG_TEXT, ""))
    return {CONFIG_REL: config_entry, HOOKS_REL: hook_entry}, []
