"""Idempotent managed blocks inside user-owned files.

Markdown files use HTML comments:
    <!-- PROJECT-STEWARD:BEGIN name -->
    ...
    <!-- PROJECT-STEWARD:END name -->

Plain-text files (e.g. .gitignore) use hash comments:
    # PROJECT-STEWARD:BEGIN name
    ...
    # PROJECT-STEWARD:END name

Rules: never touch text outside a block; updates are idempotent; diffs are
produced for review before writing top-level instruction files.
"""
from __future__ import annotations

import difflib
import re

from . import BLOCK_PREFIX, StewardError

STYLES = {
    "html": ("<!-- {prefix}:BEGIN {name} -->", "<!-- {prefix}:END {name} -->"),
    "hash": ("# {prefix}:BEGIN {name}", "# {prefix}:END {name}"),
}

# Marker lines may carry trailing spaces or tabs: editors add them, and a
# single stray space must not make a block invisible (which would append a
# duplicate instead of updating in place).
MARKER_LINE_RE = re.compile(
    r"^(?:"
    r"<!-- (?P<html_prefix>PROJECT-STEWARD):"
    r"(?P<html_kind>BEGIN|END) (?P<html_name>[\w.-]+) -->"
    r"|"
    r"# (?P<hash_prefix>PROJECT-STEWARD):"
    r"(?P<hash_kind>BEGIN|END) (?P<hash_name>[\w.-]+)"
    r")[ \t]*(?:\r?\n)?$"
)

_MARKER_LIKE_PREFIXES = (
    "<!-- " + BLOCK_PREFIX + ":",
    "# " + BLOCK_PREFIX + ":",
)


class MarkerError(StewardError):
    """Managed markers are malformed, duplicated, nested, or unclosed.

    A StewardError, so the CLI reports it and exits 1 rather than writing a
    file it cannot safely update.
    """


def _marker_parts(match):
    if match.group("html_prefix"):
        return {"style": "html", "prefix": match.group("html_prefix"),
                "kind": match.group("html_kind"),
                "name": match.group("html_name")}
    return {"style": "hash", "prefix": match.group("hash_prefix"),
            "kind": match.group("hash_kind"),
            "name": match.group("hash_name")}


def validate_blocks(text, label="file"):
    """Raise MarkerError unless every managed marker is well formed.

    Guards the write path: refusing beats appending a second copy of a block
    or writing across a half-open one.
    """
    lines = text.splitlines(True)
    if text and not lines:
        lines = [text]
    open_marker = None
    seen = set()
    for index, line in enumerate(lines):
        match = MARKER_LINE_RE.match(line)
        if not match:
            stripped = line.strip()
            if any(stripped.startswith(p) for p in _MARKER_LIKE_PREFIXES):
                raise MarkerError(
                    "%s has a malformed managed marker on line %d"
                    % (label, index + 1))
            continue
        marker = _marker_parts(match)
        if marker["kind"] == "BEGIN":
            if open_marker is not None:
                raise MarkerError("%s has nested managed markers on line %d"
                                  % (label, index + 1))
            if marker["name"] in seen:
                raise MarkerError(
                    "%s has duplicate managed marker block %s — remove the "
                    "extra copy before re-running" % (label, marker["name"]))
            seen.add(marker["name"])
            open_marker = marker
            continue
        if open_marker is None:
            raise MarkerError("%s has an END marker without a BEGIN on line %d"
                              % (label, index + 1))
        if (marker["style"], marker["prefix"], marker["name"]) != (
                open_marker["style"], open_marker["prefix"],
                open_marker["name"]):
            raise MarkerError("%s has mismatched managed markers ending on "
                              "line %d" % (label, index + 1))
        open_marker = None
    if open_marker is not None:
        raise MarkerError("%s has an unclosed managed marker block %s"
                          % (label, open_marker["name"]))
    return True


def _newline_for(text, default="\n"):
    """The file's own line ending, taken from its FIRST terminated line.

    Not "any CRLF present": one stray CRLF in a mostly-LF file must not flip
    the whole block to CRLF.
    """
    for line in text.splitlines(True):
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
    return default


def markers(name, style="html", prefix=BLOCK_PREFIX):
    begin_tpl, end_tpl = STYLES[style]
    return (
        begin_tpl.format(prefix=prefix, name=name),
        end_tpl.format(prefix=prefix, name=name),
    )


def _block_re(name, style="html", prefix=BLOCK_PREFIX):
    begin, end = markers(name, style, prefix)
    return re.compile(
        re.escape(begin) + r"[ \t]*\r?\n(.*?)" + re.escape(end) + r"[ \t]*",
        flags=re.DOTALL,
    )


def get_block(text, name, style="html", prefix=BLOCK_PREFIX):
    match = _block_re(name, style, prefix).search(text)
    return match.group(1).rstrip("\r\n") if match else None


def has_block(text, name, style="html", prefix=BLOCK_PREFIX):
    return get_block(text, name, style, prefix) is not None


def upsert_block(text, name, content, style="html", label="file"):
    """Replace the named block's body, or append the block at end of file.

    Refuses (MarkerError) when the existing markers are not well formed.
    """
    validate_blocks(text, label)
    begin, end = markers(name, style)
    newline = _newline_for(text)
    body = content.rstrip("\r\n").replace("\r\n", "\n")
    if newline == "\r\n":
        body = body.replace("\n", newline)
    rendered = "%s%s%s%s%s" % (begin, newline, body, newline, end)
    pattern = _block_re(name, style)
    if pattern.search(text):
        return pattern.sub(lambda _m: rendered, text, count=1)
    if text:
        if text.endswith(newline + newline):
            separator = ""
        elif text.endswith(newline):
            separator = newline
        else:
            separator = newline + newline
        return text + separator + rendered + newline
    return rendered + newline


def remove_block(text, name, style="html", prefix=BLOCK_PREFIX):
    pattern = re.compile(
        r"\n?" + _block_re(name, style, prefix).pattern + r"\n?",
        flags=re.DOTALL,
    )
    return pattern.sub("\n", text, count=1)


def list_blocks(text, prefix=BLOCK_PREFIX):
    names = set()
    for style in STYLES:
        for match in re.finditer(_begin_regex(style, prefix), text):
            names.add(match.group(1))
    return sorted(names)


def _begin_regex(style, prefix):
    begin_tpl, _ = STYLES[style]
    escaped = re.escape(begin_tpl.format(prefix=prefix, name="\x00"))
    return escaped.replace(re.escape("\x00"), r"([\w.-]+)")


def unified_diff(old, new, path):
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a/%s" % path,
            tofile="b/%s" % path,
        )
    )
