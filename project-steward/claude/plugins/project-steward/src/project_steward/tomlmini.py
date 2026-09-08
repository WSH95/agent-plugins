r"""Minimal TOML subset reader for Python 3.7-3.10 (tomllib used on 3.11+).

Supports exactly what Project Steward's config.toml needs:
  * ``[section]`` and ``[a.b]`` tables (nested dicts)
  * ``key = "string"`` (standard TOML escapes, decoded and validated the
    same way tomllib does) / ``'literal string'`` / integer / float /
    true / false
  * full-line and trailing ``#`` comments (quote-aware)
It intentionally does NOT support arrays, multi-line strings, dates, or
inline tables. Keep config.toml flat and simple; use single-quoted
literal strings for Windows paths (``dir = 'C:\Users\me'``).
"""
from __future__ import annotations

import re


class TomlMiniError(ValueError):
    pass


# TOML forbids leading zeros, and spells booleans in lower case only. These
# are the checks that keep 3.7-3.10 agreeing with tomllib on 3.11+: a config
# that parses here must parse there, and vice versa.
_INT_RE = re.compile(r"^[+-]?(0|[1-9](_?[0-9])*)$")
_FLOAT_RE = re.compile(
    r"^[+-]?("
    r"(0|[1-9](_?[0-9])*)(\.[0-9](_?[0-9])*)?([eE][+-]?[0-9](_?[0-9])*)"
    r"|(0|[1-9](_?[0-9])*)\.[0-9](_?[0-9])*"
    r"|inf|nan"
    r")$"
)


def _split_key(raw, lineno):
    """Split a dotted and/or quoted key into its segments.

    `a.b = 1` nests exactly as tomllib nests it; `"a.b"` stays one segment.
    """
    segments = []
    buf = []
    quote = ""
    escaped = False
    for char in raw.strip():
        if escaped:
            buf.append(char)
            escaped = False
            continue
        if quote:
            if char == "\\" and quote == '"':
                escaped = True
                continue
            if char == quote:
                quote = ""
                continue
            buf.append(char)
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == ".":
            segments.append("".join(buf))
            buf = []
            continue
        if char.isspace():
            continue
        buf.append(char)
    if quote:
        raise TomlMiniError("line %d: unterminated quoted key" % lineno)
    segments.append("".join(buf))
    if any(not seg for seg in segments):
        raise TomlMiniError("line %d: empty key segment" % lineno)
    return segments


def _strip_comment(line):
    out = []
    quote = None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).strip()


_BASIC_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r",
                  '"': '"', "\\": "\\"}


def _unescape_basic(raw, lineno):
    # Decode basic-string escapes exactly as strictly as tomllib so the
    # same config.toml parses identically on 3.7-3.10 and 3.11+.
    out = []
    idx = 0
    while idx < len(raw):
        ch = raw[idx]
        if ch != "\\":
            out.append(ch)
            idx += 1
            continue
        idx += 1
        if idx >= len(raw):
            raise TomlMiniError("line %d: dangling backslash" % lineno)
        esc = raw[idx]
        if esc in _BASIC_ESCAPES:
            out.append(_BASIC_ESCAPES[esc])
            idx += 1
            continue
        if esc in ("u", "U"):
            width = 4 if esc == "u" else 8
            digits = raw[idx + 1:idx + 1 + width]
            try:
                if len(digits) != width:
                    raise ValueError(digits)
                out.append(chr(int(digits, 16)))
            except ValueError:
                raise TomlMiniError(
                    "line %d: bad \\%s escape" % (lineno, esc))
            idx += 1 + width
            continue
        raise TomlMiniError("line %d: invalid escape \\%s" % (lineno, esc))
    return "".join(out)


def _parse_value(raw, lineno):
    raw = raw.strip()
    if not raw:
        raise TomlMiniError("line %d: empty value" % lineno)
    if raw[0] in ("'", '"'):
        if len(raw) < 2 or raw[-1] != raw[0]:
            raise TomlMiniError("line %d: unterminated string" % lineno)
        body = raw[1:-1]
        return body if raw[0] == "'" else _unescape_basic(body, lineno)
    if raw in ("true", "false"):
        return raw == "true"
    if raw.lower() in ("true", "false"):
        raise TomlMiniError(
            "line %d: booleans are lower case in TOML (%r)" % (lineno, raw))
    if _INT_RE.match(raw):
        return int(raw.replace("_", ""))
    if _FLOAT_RE.match(raw):
        return float(raw.replace("_", ""))
    raise TomlMiniError("line %d: unsupported value %r" % (lineno, raw))


def loads(text):
    root = {}
    table = root
    defined_tables = set()
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw_line)
        if not line:
            continue
        if line.startswith("["):
            if line.startswith("[["):
                raise TomlMiniError(
                    "line %d: arrays of tables are not supported" % lineno)
            if not line.endswith("]"):
                raise TomlMiniError("line %d: bad table header" % lineno)
            name = line[1:-1].strip()
            if not name:
                raise TomlMiniError("line %d: empty table name" % lineno)
            segments = tuple(_split_key(name, lineno))
            if segments in defined_tables:
                raise TomlMiniError(
                    "line %d: table [%s] is defined twice" % (lineno, name))
            defined_tables.add(segments)
            table = root
            for part in segments:
                table = table.setdefault(part, {})
                if not isinstance(table, dict):
                    raise TomlMiniError("line %d: table/key clash" % lineno)
            continue
        if "=" not in line:
            raise TomlMiniError("line %d: expected key = value" % lineno)
        key, _, value = line.partition("=")
        segments = _split_key(key, lineno)
        target = table
        for part in segments[:-1]:
            target = target.setdefault(part, {})
            if not isinstance(target, dict):
                raise TomlMiniError("line %d: key/table clash" % lineno)
        leaf = segments[-1]
        if leaf in target:
            raise TomlMiniError(
                "line %d: duplicate key %s" % (lineno, leaf))
        target[leaf] = _parse_value(value, lineno)
    return root


def _has_array_of_tables(text):
    return any(line.strip().startswith("[[") for line in text.splitlines())


def load_toml_text(text):
    """Parse TOML text with tomllib when available, else the mini reader.

    Both paths answer identically. tomllib understands arrays of tables and
    the mini reader does not, so they are refused on both rather than
    letting a config parse on 3.11+ and fail below it.
    """
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return loads(text)
    if _has_array_of_tables(text):
        raise TomlMiniError("arrays of tables are not supported")
    return tomllib.loads(text)
