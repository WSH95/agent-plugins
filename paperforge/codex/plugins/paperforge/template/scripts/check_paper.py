#!/usr/bin/env python3
"""Deterministic consistency checks for the LaTeX manuscript.

Checks (stdlib only, heuristic but useful):
  1. \\cite keys missing from refs.bib (ERROR) / unused bib entries (WARN)
  2. \\ref/\\eqref/\\autoref/\\cref to missing labels (ERROR) / unused labels (WARN)
  3. \\todo{...} inventory (INFO)
  4. Acronyms used but never defined as "Full Name (ACRO)" (WARN);
     pluralized definitions "(ACROs)" count, and \\todo{...} content is
     exempt from the prose scans
  5. Terminology variants that should be consistent, e.g. "sim-to-real" (WARN)
  6. Doubled words ("the the") (WARN)
  7. Sentences starting with a digit (WARN; paragraph-aware — wrapped
     source lines are joined before the test)
  8. Evidence tags (% evidence: E3) that have no row in evidence/results.md
     (ERROR), and duplicate row IDs in evidence/results.md (ERROR)

Exit code 1 if any ERROR was found, else 0. Run from the repo root:
    python3 scripts/check_paper.py [manuscript_dir]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- config ---

# Acronyms that need no definition in this project. Extend freely.
ACRONYM_WHITELIST = {
    "USA", "GPU", "CPU", "RAM", "URL", "DOI", "PDF", "FPS", "IMU",
    "II", "III", "IV", "VI", "VII", "TODO",
}

# Groups of spellings that must not be mixed. First item = canonical.
TERM_VARIANTS = [
    ["sim-to-real", "sim to real", "Sim2Real", "sim2real"],
    ["state-of-the-art", "state of the art"],
    ["end-to-end", "end to end"],
    ["real-world", "real world"],  # adjective vs. noun: review hits manually
]

SECTION_ORDER_HINT = re.compile(r"(\d+)")  # sections sort by leading number

# ---------------------------------------------------------------- helpers --


def strip_comments(line: str) -> str:
    """Remove LaTeX comments while preserving escaped percent signs."""
    out, i = [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            out.append(line[i : i + 2])
            i += 2
            continue
        if ch == "%":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def strip_todos(line: str, depth: int) -> tuple[str, int]:
    """Remove \\todo{...} spans from prose (brace-balanced; may span lines).

    Todo text is a workflow annotation, not manuscript prose — acronym,
    terminology, doubled-word, and digit-start scans must not fire on it.
    `depth` carries an unclosed todo's brace depth into the next line;
    returns (cleaned_line, new_depth).
    """
    out, i = [], 0
    while i < len(line):
        if depth:
            ch = line[i]
            if ch == "\\" and i + 1 < len(line):
                i += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
            continue
        if line.startswith("\\todo{", i):
            depth = 1
            i += len("\\todo{")
            continue
        if line[i] == "\\" and i + 1 < len(line):
            out.append(line[i : i + 2])
            i += 2
            continue
        out.append(line[i])
        i += 1
    return "".join(out), depth


def tex_files(root: Path):
    files = [p for p in root.rglob("*.tex")]

    def key(p: Path):
        m = SECTION_ORDER_HINT.search(p.stem)
        return (0, int(m.group(1))) if m and "sections" in p.parts else (1, 0)

    return sorted(files, key=key)


def load_bib_keys(bib: Path):
    if not bib.exists():
        return set()
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", bib.read_text(errors="ignore")))


def load_evidence_ids(results: Path):
    """Return (ids, duplicates) from the evidence table's ID column."""
    ids, dupes = set(), set()
    if not results.exists():
        return ids, dupes
    for line in results.read_text(errors="ignore").splitlines():
        m = re.match(r"^\|\s*(E\d+)\s*\|", line)
        if m:
            (dupes if m.group(1) in ids else ids).add(m.group(1))
    return ids, dupes


# ---------------------------------------------------------------- main -----


def main() -> int:
    manuscript = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("manuscript")
    if not manuscript.exists():
        print(f"ERROR: manuscript directory not found: {manuscript}")
        return 1

    errors, warnings, infos = [], [], []

    cites, labels, refs, todos, ev_refs = {}, {}, {}, [], {}
    acro_used, acro_defined = {}, set()
    variant_counts = {v: 0 for group in TERM_VARIANTS for v in group}
    doubles, digit_starts = [], []

    cite_re = re.compile(r"\\cite[tp]?\*?(?:\[[^\]]*\])?\{([^}]*)\}")
    label_re = re.compile(r"\\label\{([^}]*)\}")
    ref_re = re.compile(r"\\(?:auto|eq|c|C)?ref\*?\{([^}]*)\}")
    todo_re = re.compile(r"\\todo\{([^}]*)\}")
    acro_def_re = re.compile(r"\(([A-Z][A-Za-z]{1,7})s?\)")
    acro_use_re = re.compile(r"\b([A-Z]{2,6})s?\b")
    double_re = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
    digit_start_re = re.compile(r"[.!?]\s+(\d[\d.,]*\s+\w)")
    digit_para_start_re = re.compile(r"\d[\d.,]*\s+\w")
    ev_tag_re = re.compile(r"%\s*evidence:\s*([E0-9,\s]+)", re.IGNORECASE)

    seen_position = 0
    for path in tex_files(manuscript):
        rel = path.relative_to(manuscript.parent) if manuscript.parent != Path(".") else path
        todo_depth = 0
        para: list = []  # (lineno, prose) — one LaTeX paragraph, joined for digit scan

        def flush_para(para=para, rel=rel):
            if not para:
                return
            joined = " ".join(t for _, t in para)
            starts, pos = [], 0
            for ln, t in para:
                starts.append((pos, ln))
                pos += len(t) + 1

            def line_of(off):
                return max(l for s, l in starts if s <= off)

            m0 = digit_para_start_re.match(joined)
            if m0:
                digit_starts.append((f"{rel}:{line_of(0)}", m0.group(0)))
            for m in digit_start_re.finditer(joined):
                digit_starts.append((f"{rel}:{line_of(m.start(1))}", m.group(1)))
            para.clear()

        for lineno, raw in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            # Evidence tags live inside LaTeX comments; scan before stripping.
            for m in ev_tag_re.finditer(raw):
                for k in re.findall(r"E\d+", m.group(1)):
                    ev_refs.setdefault(k, f"{rel}:{lineno}")
            line = strip_comments(raw)
            if not raw.strip():
                # A truly blank line ends a LaTeX paragraph.
                flush_para()
                continue
            if not line.strip():
                # Comment-only line: invisible to LaTeX paragraphing.
                continue
            seen_position += 1
            loc = f"{rel}:{lineno}"

            for m in cite_re.finditer(line):
                for k in (k.strip() for k in m.group(1).split(",") if k.strip()):
                    cites.setdefault(k, loc)
            for m in label_re.finditer(line):
                labels.setdefault(m.group(1).strip(), loc)
            for m in ref_re.finditer(line):
                for k in (k.strip() for k in m.group(1).split(",") if k.strip()):
                    refs.setdefault(k, loc)
            for m in todo_re.finditer(line):
                todos.append((loc, m.group(1)[:70]))

            # Prose-quality scans must not see \todo{...} annotation text.
            prose, todo_depth = strip_todos(line, todo_depth)
            for m in acro_def_re.finditer(prose):
                tok = m.group(1)
                acro_defined.add(tok.upper())
                if tok.endswith("s"):
                    # "(CIs)" defines CI as well as CIS.
                    acro_defined.add(tok[:-1].upper())
            if "macros" not in path.stem:
                for m in acro_use_re.finditer(prose):
                    a = m.group(1)
                    if a not in ACRONYM_WHITELIST:
                        acro_used.setdefault(a, (seen_position, loc))
                for group in TERM_VARIANTS:
                    for v in group:
                        variant_counts[v] += len(
                            re.findall(re.escape(v), prose, re.IGNORECASE)
                        ) if "-" in v or " " in v else len(
                            re.findall(rf"\b{re.escape(v)}\b", prose)
                        )
                for m in double_re.finditer(prose):
                    if m.group(1).lower() not in {"that"}:  # "that that" is sometimes valid
                        doubles.append((loc, m.group(0)))
                if prose.strip():
                    para.append((lineno, prose.strip()))
        flush_para()

    bib_keys = load_bib_keys(manuscript / "refs.bib")

    ev_path = manuscript.parent / "evidence" / "results.md"
    ev_ids, ev_dupes = load_evidence_ids(ev_path)
    for k in sorted(ev_dupes):
        errors.append(f"duplicate evidence ID in {ev_path}: '{k}'")
    if ev_refs and not ev_path.exists():
        warnings.append(f"evidence tags used but {ev_path} was not found")
    else:
        for k, loc in sorted(ev_refs.items()):
            if k not in ev_ids:
                errors.append(f"evidence tag '{k}' has no row in {ev_path} ({loc})")

    for k, loc in sorted(cites.items()):
        if k not in bib_keys:
            errors.append(f"cite key not in refs.bib: '{k}' (first use {loc})")
    for k in sorted(bib_keys - set(cites)):
        warnings.append(f"bib entry never cited: '{k}'")
    for k, loc in sorted(refs.items()):
        if k not in labels:
            errors.append(f"ref to missing label: '{k}' ({loc})")
    for k, loc in sorted(labels.items()):
        if k not in refs:
            warnings.append(f"label never referenced: '{k}' ({loc})")

    for a, (_, loc) in sorted(acro_used.items()):
        if a not in acro_defined:
            warnings.append(
                f"acronym '{a}' used but never defined as 'Full Name ({a})' (first use {loc})"
            )

    for group in TERM_VARIANTS:
        present = [(v, variant_counts[v]) for v in group if variant_counts[v] > 0]
        if len(present) > 1:
            detail = ", ".join(f"'{v}' x{c}" for v, c in present)
            warnings.append(f"mixed terminology (canonical: '{group[0]}'): {detail}")

    for loc, text in doubles:
        warnings.append(f"doubled word '{text}' ({loc})")
    for loc, text in digit_starts:
        warnings.append(f"sentence starts with a digit: '...{text}...' ({loc})")

    if todos:
        infos.append(f"{len(todos)} open \\todo item(s):")
        infos.extend(f"  - {loc}: {text}" for loc, text in todos)

    # ------------------------------------------------------------- report --
    for tag, items in (("ERROR", errors), ("WARN", warnings), ("INFO", infos)):
        for item in items:
            print(f"[{tag}] {item}")
    print(
        f"\nSummary: {len(errors)} error(s), {len(warnings)} warning(s), "
        f"{len(todos)} todo(s) across manuscript."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
