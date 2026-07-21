#!/usr/bin/env python3
"""Deterministic checks for a mock-review round and its area-chair meta-review.

Checks (stdlib only):
  1. state/reviews/round-N/ exists and holds at least one review file —
     every *.md except meta-review.md / revision-plan.md / response.md
     counts as a review, so keep stray notes out of round directories.
  2. meta-review.md exists; if not, the area-chair adjudication step of the
     paper-review-panel skill has not run yet (FAIL says exactly that).
  3. meta-review.md carries every required section heading (matched by
     prefix, so heading parentheticals may evolve).
  4. The "Adjudication of major weaknesses" table:
     - every verdict is one of confirmed / partly-confirmed / refuted /
       judgment-call / out-of-scope (a trailing "(contested)" marker is
       stripped first);
     - confirmed / partly-confirmed / refuted rows carry a non-empty
       Evidence cell (the area chair's evidence rule is symmetric with
       what reviewers owe the authors);
     - the Reviewer cell names a review file of the round (file stem,
       "reviewer-" prefix optional);
     - structured reviews (files with "- W1 ..." major-weakness bullets):
       every major W# has exactly one row, and no row cites an id absent
       from that review (no phantom adjudications);
     - unstructured reviews (real venue reviews saved verbatim, no W# ids)
       are reported as [warn] and need at least one adjudication row; their
       row ids are area-chair-assigned, so the phantom check does not apply.
  5. The "## Overall call" line contains accept, borderline, or reject.

Output tags are [OK]/[FAIL]/[warn]. The manuscript checker check_paper.py
uses [ERROR]/[WARN]/[INFO]; the divergence is deliberate (skills and the
smoke test reference these exact tags) — do not unify.

Exit codes: 0 clean, 1 at least one FAIL, 2 usage error. Run from the
workspace root:
    python3 scripts/check_reviews.py <round-number>
Python 3.8+; files are read as UTF-8 with errors ignored so Windows locale
defaults cannot mis-decode the em-dash headings.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- config ---

NON_REVIEW_FILES = {"meta-review.md", "revision-plan.md", "response.md"}

VERDICTS = {"confirmed", "partly-confirmed", "refuted", "judgment-call", "out-of-scope"}
EVIDENCE_REQUIRED = {"confirmed", "partly-confirmed", "refuted"}

# Matched as prefixes against meta-review.md lines.
REQUIRED_HEADINGS = [
    "# Meta-Review",
    "## Score summary",
    "## Adjudication of major weaknesses",
    "## Consensus strengths",
    "## Consensus weaknesses",
    "## Points of disagreement",
    "## Reality check",
    "## Points for the author",
    "## Top 5 must-fix",
    "## Overall call",
]

ADJUDICATION_HEADING = "## adjudication of major weaknesses"

# "## Weaknesses — major" with em dash, en dash, or hyphen.
MAJOR_HEADING_RE = re.compile(r"^##\s+Weaknesses\s*[-–—]+\s*major\s*$", re.IGNORECASE)
MAJOR_BULLET_RE = re.compile(r"^\s*[-*]\s*\**\s*(W\d+)\b")
ROW_ID_RE = re.compile(r"^[WwQ]\d+$")
CONTESTED_RE = re.compile(r"\s*\(contested\)\s*$", re.IGNORECASE)
OVERALL_CALL_RE = re.compile(r"\b(accept|borderline|reject)\b", re.IGNORECASE)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def major_ids(text: str) -> list:
    """Major weakness ids (W#) of one review, in order, deduplicated.

    Scoped to the "Weaknesses — major" section when the review has one
    (the persona rubric); otherwise any W# bullet in the file (lenient for
    hand-saved real reviews that kept ids but not the headings).
    """
    scoped, anywhere, in_major, saw_heading = [], [], False, False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_major = bool(MAJOR_HEADING_RE.match(stripped))
            saw_heading = saw_heading or in_major
            continue
        m = MAJOR_BULLET_RE.match(line)
        if m:
            anywhere.append(m.group(1))
            if in_major:
                scoped.append(m.group(1))
    ids = scoped if saw_heading else anywhere
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def adjudication_rows(text: str) -> list:
    """Cell lists of the adjudication table (header/separator rows skipped)."""
    rows, in_table = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_table = stripped.lower().startswith(ADJUDICATION_HEADING)
            continue
        if not in_table or not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or cells[0].lower() in {"w-id", "id"}:
            continue
        if all(re.fullmatch(r"[:\-\s]*", c) for c in cells):
            continue
        rows.append(cells)
    return rows


# ---------------------------------------------------------------- main -----


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("usage: python3 scripts/check_reviews.py <round-number>", file=sys.stderr)
        return 2
    round_no = sys.argv[1]
    round_dir = Path("state") / "reviews" / f"round-{round_no}"

    fails, warns = [], []

    if not round_dir.is_dir():
        print(f"[FAIL] round directory not found: {round_dir}")
        return 1

    reviews = sorted(
        p for p in round_dir.glob("*.md") if p.name not in NON_REVIEW_FILES
    )
    if not reviews:
        fails.append(f"no review files in {round_dir}")

    review_majors = {p.stem: major_ids(read_text(p)) for p in reviews}
    review_texts = {p.stem: read_text(p) for p in reviews}
    for stem, majors in sorted(review_majors.items()):
        if not majors:
            warns.append(
                f"unstructured review (no W# ids): {stem}.md — "
                "coverage not verifiable, at least one adjudication row required"
            )

    meta_path = round_dir / "meta-review.md"
    if not meta_path.is_file():
        fails.append(
            f"{meta_path} not found — run the area-chair adjudication "
            "(meta-review) step of the paper-review-panel skill"
        )
    else:
        meta = read_text(meta_path)
        meta_lines = meta.splitlines()
        for heading in REQUIRED_HEADINGS:
            if not any(l.strip().startswith(heading) for l in meta_lines):
                fails.append(f"meta-review.md is missing the '{heading}' section")

        for line in meta_lines:
            if line.strip().startswith("## Overall call"):
                if not OVERALL_CALL_RE.search(line):
                    fails.append(
                        "the '## Overall call' line names none of accept | borderline | reject"
                    )
                break

        rows_by_review = {stem: [] for stem in review_majors}
        for cells in adjudication_rows(meta):
            if len(cells) < 3:
                fails.append(f"adjudication row has fewer than 3 cells: {cells}")
                continue
            row_id, reviewer, verdict = cells[0], cells[1], cells[2]
            evidence = cells[3] if len(cells) > 3 else ""

            if not ROW_ID_RE.fullmatch(row_id):
                fails.append(f"adjudication row id '{row_id}' is not a W#/w#/Q# id")
                continue

            stem = None
            reviewer_l = reviewer.lower()
            for cand in review_majors:
                if reviewer_l == cand.lower() or f"reviewer-{reviewer_l}" == cand.lower():
                    stem = cand
                    break
            if stem is None:
                fails.append(
                    f"adjudication row {row_id} names unknown reviewer '{reviewer}' "
                    f"(no such review file in {round_dir})"
                )
                continue
            rows_by_review[stem].append(row_id)

            bare = CONTESTED_RE.sub("", verdict).strip().lower()
            if bare not in VERDICTS:
                fails.append(
                    f"verdict '{verdict}' on {row_id} ({stem}) is not in the vocabulary "
                    f"{{{' | '.join(sorted(VERDICTS))}}}"
                )
            elif bare in EVIDENCE_REQUIRED and evidence.strip("-— ") == "":
                fails.append(
                    f"verdict '{bare}' on {row_id} ({stem}) has an empty Evidence cell"
                )

            if review_majors[stem] and not re.search(
                rf"\b{re.escape(row_id)}\b", review_texts[stem]
            ):
                fails.append(
                    f"phantom adjudication: {stem}.md contains no id '{row_id}'"
                )

        for stem, majors in sorted(review_majors.items()):
            got = rows_by_review[stem]
            if majors:
                for wid in majors:
                    n = got.count(wid)
                    if n == 0:
                        fails.append(f"{wid} ({stem}) has no adjudication row")
                    elif n > 1:
                        fails.append(f"{wid} ({stem}) has {n} adjudication rows, expected 1")
            elif not got:
                fails.append(f"unstructured review {stem}.md has no adjudication row at all")

    # ------------------------------------------------------------- report --
    for item in fails:
        print(f"[FAIL] {item}")
    for item in warns:
        print(f"[warn] {item}")
    if not fails:
        print(
            f"[OK] round {round_no}: {len(reviews)} review file(s); meta-review "
            "headings, verdicts, and adjudication coverage check out"
        )
    print(f"Summary: {len(fails)} error(s), {len(warns)} warning(s) in {round_dir}/.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
