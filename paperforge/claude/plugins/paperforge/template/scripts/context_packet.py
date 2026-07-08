#!/usr/bin/env python3
"""Build a compact Markdown context packet for chat-based sessions.

Useful when working outside a repo-native agent (e.g., pasting into claude.ai
or ChatGPT on a phone): bundles the project brief, style sheet, progress
board, curated evidence, and one manuscript section into a single document.

Usage (from the repo root):
    python3 scripts/context_packet.py --section introduction
    python3 scripts/context_packet.py --section experiments --task "polish pass"
    python3 scripts/context_packet.py --section method --output state/method-packet.md

Stdlib only. Prints to stdout unless --output is given.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

STATE_FILES = [
    ("Project brief", "state/project.md"),
    ("Style constraints", "state/style.md"),
    ("Progress board and open questions", "state/progress.md"),
    ("Curated evidence", "evidence/results.md"),
]

AGENT_INSTRUCTIONS = """\
You are assisting on the section above of a long-running academic paper.
Rules: ground every number in the Curated evidence section (never invent or
extrapolate values); do not add or strengthen claims beyond the Project brief;
follow the Style constraints; when intent is unclear, ask ONE question instead
of guessing; propose edits as surgical diffs, not full rewrites.
"""


def read(path: Path) -> str | None:
    try:
        return path.read_text(errors="ignore").strip()
    except OSError:
        return None


def find_section(root: Path, section: str) -> Path | None:
    """Locate a section .tex file by fuzzy name match; None if ambiguous/missing."""
    candidates = sorted(root.glob("manuscript/**/*.tex"))
    needle = section.lower().replace(" ", "_")
    hits = [p for p in candidates if needle in p.stem.lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        print(f"No section file matching '{section}'. Candidates:", file=sys.stderr)
    else:
        print(f"Ambiguous section '{section}'. Candidates:", file=sys.stderr)
        candidates = hits
    for p in candidates:
        print(f"  - {p}", file=sys.stderr)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--section", required=True, help="section name, e.g. introduction")
    ap.add_argument("--task", default="draft/revise", help="what the packet is for")
    ap.add_argument("--output", default=None, help="write to file instead of stdout")
    args = ap.parse_args()

    root = Path.cwd()
    if not (root / "state").is_dir():
        print("Run from the repository root (state/ not found).", file=sys.stderr)
        return 1

    parts = [f"# Context packet — section: {args.section} — task: {args.task}\n"]
    for title, rel in STATE_FILES:
        text = read(root / rel)
        parts.append(f"## {title} ({rel})\n\n" + (text if text else "_missing_") + "\n")

    sec = find_section(root, args.section)
    if sec is not None:
        parts.append(f"## Current section text ({sec})\n\n```latex\n{read(sec)}\n```\n")
    else:
        parts.append("## Current section text\n\n_not resolved — see stderr_\n")

    parts.append("## Agent instructions\n\n" + AGENT_INSTRUCTIONS)
    packet = "\n".join(parts)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(packet)
        print(f"Wrote {out} ({len(packet)} chars)", file=sys.stderr)
    else:
        print(packet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
