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

from . import BLOCK_PREFIX, LEGACY_BLOCK_PREFIX

STYLES = {
    "html": ("<!-- {prefix}:BEGIN {name} -->", "<!-- {prefix}:END {name} -->"),
    "hash": ("# {prefix}:BEGIN {name}", "# {prefix}:END {name}"),
}


def markers(name, style="html", prefix=BLOCK_PREFIX):
    begin_tpl, end_tpl = STYLES[style]
    return (
        begin_tpl.format(prefix=prefix, name=name),
        end_tpl.format(prefix=prefix, name=name),
    )


def _block_re(name, style="html", prefix=BLOCK_PREFIX):
    begin, end = markers(name, style, prefix)
    return re.compile(
        re.escape(begin) + r"\n(.*?)" + re.escape(end),
        flags=re.DOTALL,
    )


def get_block(text, name, style="html", prefix=BLOCK_PREFIX):
    match = _block_re(name, style, prefix).search(text)
    return match.group(1).rstrip("\n") if match else None


def has_block(text, name, style="html", prefix=BLOCK_PREFIX):
    return get_block(text, name, style, prefix) is not None


def upsert_block(text, name, content, style="html"):
    """Replace the named block's body, or append the block at end of file."""
    begin, end = markers(name, style)
    body = content.rstrip("\n")
    rendered = "%s\n%s\n%s" % (begin, body, end)
    pattern = _block_re(name, style)
    if pattern.search(text):
        return pattern.sub(lambda _m: rendered, text, count=1)
    base = text.rstrip("\n")
    if base:
        return base + "\n\n" + rendered + "\n"
    return rendered + "\n"


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


def find_legacy_blocks(text):
    """Names of old PROJECTFORGE blocks present in *text* (any style)."""
    names = set()
    for style in STYLES:
        for match in re.finditer(_begin_regex(style, LEGACY_BLOCK_PREFIX), text):
            names.add(match.group(1))
    return sorted(names)


def convert_legacy_markers(text):
    """Rewrite PROJECTFORGE block markers to PROJECT-STEWARD markers."""
    return text.replace(LEGACY_BLOCK_PREFIX + ":BEGIN", BLOCK_PREFIX + ":BEGIN") \
               .replace(LEGACY_BLOCK_PREFIX + ":END", BLOCK_PREFIX + ":END")


def unified_diff(old, new, path):
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a/%s" % path,
            tofile="b/%s" % path,
        )
    )
