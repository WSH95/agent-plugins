"""Surgical JSONC settings edits using only the Python standard library."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

DEFAULTS = {
    "latex-workshop.latex.autoBuild.run": "onFileChange",
    "latex-workshop.view.pdf.viewer": "tab",
}
TOKEN = re.compile(r'\s+|//[^\r\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|'
                   r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|'
                   r'true|false|null|[{}\[\],:]', re.DOTALL)


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate settings key: " + key)
        result[key] = value
    return result


def parse(text):
    """Validate JSONC and return its object and significant token spans."""
    tokens, masked, pos = [], list(text), 0
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match:
            raise ValueError("Invalid JSONC near character %d" % pos)
        word = match.group()
        if word.isspace() or word.startswith(("//", "/*")):
            if not word.isspace():
                masked[pos:match.end()] = " " * (match.end() - pos)
        else:
            tokens.append((word, pos, match.end()))
        pos = match.end()
    for index, token in enumerate(tokens[:-1]):
        if token[0] == "," and tokens[index + 1][0] in ("}", "]"):
            masked[token[1]] = " "
    value = json.loads("".join(masked), object_pairs_hook=pairs) if tokens else {}
    if not isinstance(value, dict):
        raise ValueError("VS Code settings must be a JSON object")
    return value, tokens


def updated(text, changes):
    values, tokens = parse(text)
    wanted = {key: val for key, val in changes.items() if key not in values or values[key] != val}
    if not wanted:
        return text
    if not tokens:
        return updated(text + ("\n" if text else "") + "{}\n", changes)
    edits, properties = [], {}
    index, last_end = 1, None
    while index < len(tokens) - 1:
        key = json.loads(tokens[index][0])
        start = index + 2
        end, depth = start, 0
        while end < len(tokens):
            word = tokens[end][0]
            if word in ("{", "["):
                depth += 1
            elif word in ("}", "]"):
                depth -= 1
            end += 1
            if depth == 0:
                break
        properties[key] = (tokens[start][1], tokens[end - 1][2])
        last_end = end
        index = end + (1 if tokens[end][0] == "," else 0)
    for key in wanted.keys() & properties.keys():
        start, end = properties[key]
        edits.append((start, end, json.dumps(wanted[key])))
    missing = [key for key in wanted if key not in properties]
    if missing:
        addition = "\n" + ",\n".join("    %s: %s" % (json.dumps(k), json.dumps(wanted[k]))
                                              for k in missing) + "\n"
        close = tokens[-1][1]
        edits.append((close, close, addition))
        if last_end is not None and tokens[last_end][0] != ",":
            after = tokens[last_end - 1][2]
            edits.append((after, after, ","))
    for start, end, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    parse(text)
    return text


def validate_path(path):
    if path.is_symlink():
        raise ValueError("Settings is a symlink; choose its real target explicitly: " + str(path))
    original = path.read_bytes() if path.exists() else None
    parse(original.decode("utf-8") if original is not None else "")
    return original


def configure(path, changes=None):
    path = Path(path)
    original = validate_path(path)
    text = original.decode("utf-8") if original is not None else ""
    new = updated(text, DEFAULTS if changes is None else changes).encode("utf-8")
    result = {"path": str(path), "changed": new != original, "backup": None}
    if new == original:
        return result
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".paperforge-settings-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(new)
            stream.flush()
            os.fsync(stream.fileno())
        if original is not None:
            os.chmod(temporary, path.stat().st_mode & 0o777)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup = path.with_name(path.name + ".paperforge-backup-" + stamp)
            with backup.open("xb") as stream:
                stream.write(original)
            os.chmod(backup, path.stat().st_mode & 0o777)
            result["backup"] = str(backup)
        if path.is_symlink() or (path.read_bytes() if path.exists() else None) != original:
            raise ValueError("Settings changed during setup; retry after the editor finishes saving")
        if original is None:
            # Exclusive creation prevents replacing a settings file created concurrently.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result
