#!/usr/bin/env python3
"""Resolve the confirmed paper layout; show it or build without a Makefile.

Usage: python3 scripts/workspace.py {show,pdf,clean}
Optional state/workspace.json contains main_tex, bibliographies, paper_paths.
All paths are workspace-relative; main_tex and bibliographies are included
automatically. paper_paths names additional files or directories, not globs.
Without a mapping, the conventional manuscript/ layout is used. Stdlib, 3.8+.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


CONFIG = "state/workspace.json"
PRIVATE_DIRS = {"state", "evidence", ".git", ".claude", ".codex", ".agents",
                ".project-steward", "__pycache__"}
BUILD_SUFFIXES = {".aux", ".bbl", ".blg", ".fdb_latexmk", ".fls", ".log",
                  ".out", ".gz", ".toc", ".nav", ".snm", ".pyc"}


class WorkspaceError(ValueError):
    """An actionable layout error, suitable for a command's stderr."""


@dataclass
class Workspace:
    root: Path
    main_tex: Path
    bibliographies: list
    files: list

    @property
    def tex_files(self):
        return [p for p in self.files if p.suffix.lower() == ".tex"]

    @property
    def source_root(self):
        # Use a common ancestor so ../ links between approved files keep working
        # inside the review snapshot, even when the main file is in a subdir.
        return Path(os.path.commonpath([str(p.parent) for p in self.files]))

    def relative(self, path):
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            # Only the checker's legacy explicit-directory override may point
            # outside the workspace; configured review inputs never do.
            return str(path)

    def describe(self):
        return {"main_tex": self.relative(self.main_tex),
                "bibliographies": [self.relative(p) for p in self.bibliographies],
                "files": [self.relative(p) for p in self.files]}


def _path(root, value, field):
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError(f"{CONFIG}: {field} needs a non-empty relative path")
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise WorkspaceError(f"{CONFIG}: {field} must name a path inside the workspace, not {value!r}")
    if any(part in PRIVATE_DIRS for part in rel.parts):
        raise WorkspaceError(f"{CONFIG}: {field} cannot include private/tooling path {value!r}")
    path = root / rel
    for part in [path] + list(path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise WorkspaceError(f"{CONFIG}: {field} uses a symlink: {value!r}; select regular paper files")
    if not path.exists():
        raise WorkspaceError(f"{CONFIG}: {field} path not found: {value}")
    return path


def _list(config, field):
    value = config.get(field)
    if not isinstance(value, list):
        raise WorkspaceError(f"{CONFIG}: {field} must be a list of relative paths")
    return value


def load_workspace(root=None, manuscript_dir=None):
    root = Path(root or Path.cwd()).resolve()
    config_path = root / CONFIG
    if manuscript_dir is not None:
        # Preserve check_paper.py's explicit directory override. Evidence still
        # belongs to the workspace, not that directory's parent.
        directory = (root / manuscript_dir).resolve()
        if not directory.is_dir():
            raise WorkspaceError(f"manuscript directory not found: {manuscript_dir}")
        bib = directory / "refs.bib"
        return Workspace(root, directory / "main.tex", [bib] if bib.is_file() else [],
                         sorted(directory.rglob("*.tex")))
    elif config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise WorkspaceError(f"Cannot read {CONFIG}: {exc}")
        if not isinstance(config, dict):
            raise WorkspaceError(f"{CONFIG} must be a JSON object")
        unknown = set(config) - {"main_tex", "bibliographies", "paper_paths"}
        if unknown:
            raise WorkspaceError(f"{CONFIG}: unknown field(s): {', '.join(sorted(unknown))}")
    else:
        if not (root / "manuscript/main.tex").is_file():
            raise WorkspaceError(
                f"Paper layout is not configured. Confirm the paper's files with "
                f"paperforge-workspace and save {CONFIG} (main_tex, bibliographies, paper_paths).")
        config = {"main_tex": "manuscript/main.tex",
                  "bibliographies": ["manuscript/refs.bib"], "paper_paths": ["manuscript"]}

    main = _path(root, config.get("main_tex"), "main_tex")
    if not main.is_file() or main.suffix.lower() != ".tex":
        raise WorkspaceError(f"{CONFIG}: main_tex must name a .tex file")
    bibs = [_path(root, b, "bibliographies") for b in _list(config, "bibliographies")]
    if any(not b.is_file() or b.suffix.lower() != ".bib" for b in bibs):
        raise WorkspaceError(f"{CONFIG}: bibliographies must name .bib files")
    files = {main, *bibs}
    for value in _list(config, "paper_paths"):
        path = _path(root, value, "paper_paths")
        if path.is_file():
            files.add(path)
            continue
        for directory, dirs, names in os.walk(str(path)):
            dirs[:] = sorted(d for d in dirs if d not in PRIVATE_DIRS and not d.startswith("."))
            for d in dirs:
                _path(root, str((Path(directory) / d).relative_to(root)), "paper_paths")
            for name in sorted(names):
                candidate = Path(directory) / name
                if (name.startswith(".") or candidate.suffix in BUILD_SUFFIXES
                        or ".bak-" in name or name.endswith("~")
                        or candidate == main.with_suffix(".pdf")):
                    continue
                files.add(_path(root, str(candidate.relative_to(root)), "paper_paths"))
    return Workspace(root, main, sorted(set(bibs), key=lambda p: p.as_posix()),
                     sorted(files, key=lambda p: p.as_posix()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("show", "pdf", "clean"))
    args = parser.parse_args()
    try:
        workspace = load_workspace()
        if args.action == "show":
            print(json.dumps(workspace.describe(), indent=2, ensure_ascii=False))
            return 0
        latexmk = shutil.which("latexmk")
        if not latexmk:
            raise WorkspaceError("latexmk not found — install a TeX distribution (e.g. TeX Live) "
                                 "to build/clean the PDF. Checking and review work without LaTeX.")
        return subprocess.call([latexmk, "-pdf" if args.action == "pdf" else "-C",
                                "-cd", str(workspace.main_tex)])
    except (WorkspaceError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
