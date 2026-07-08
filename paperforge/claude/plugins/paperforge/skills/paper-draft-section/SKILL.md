---
name: paper-draft-section
description: Draft or substantially rewrite one section of the paper (abstract, introduction, related work, method, experiments, discussion, conclusion/limitations; also a combined results-and-discussion section for journal profiles). Use whenever the author says "draft/write/redo the <section>", "turn the outline into text", or asks for section text in any phrasing. Enforces grounding (numbers from evidence/, citations from refs.bib) and one-question clarification gates. For the related-work section, prefer the paper-related-work skill. The section architecture (which sections exist) is set by paper-outline from the venue/paper-type profile.
---

# Draft a Section

Produce publication-grade LaTeX for exactly one section per invocation, grounded in
the project's recorded intent and evidence. One section at a time keeps diffs
reviewable and keeps the author in control.

## Pre-flight gate (run before writing a single sentence)

1. `state/outline.md` covers this section → if not, offer to run `paper-outline`
   (drafting without an outline is how structural rewrites happen).
2. `state/interview.md` covers this section's intent → if a needed intent is missing,
   ask **one** question now (mini-intake, see `paper-intake`) rather than guessing.
3. Every number the outline promises for this section has a row in
   `evidence/results.md` → missing numbers become `\todo{NUMBER: ...}` plus a line
   under Open questions in `state/progress.md`. Never invent or extrapolate.
4. Read `state/style.md` and `manuscript/macros.tex`; use the macros for notation.

## Drafting procedure

1. Read the blueprint for this section type in `references/section-protocols.md`
   (read only the relevant part).
2. Draft into `manuscript/sections/<file>.tex`, one paragraph per outline topic
   sentence. Keep the outline's `%` topic-sentence comments in place above each
   paragraph — they document intent for future edits.
3. **Self-audit before showing the author** (do this silently, fix what fails):
   - Every quantitative statement traces to an evidence row (spot-check each
     one) and carries a `% evidence: E<n>` comment on its line in the source.
   - Every `\cite` key exists in `refs.bib` (grep it).
   - Claims match `state/project.md` in strength — no silent escalation. Calibrate
     each claim to the evidence rung it earns using the `paper-polish` skill's
     `references/claim-calibration.md` (causal-verb precision; the statistical
     claim-word gates — e.g. "outperforms" needs a CI-backed comparison, else
     "improves upon").
   - Style sheet compliance (banned phrases, tense, terminology).
4. Present: the drafted text, then a 3–5 line delta summary — what was written,
   which decisions were made, which `\todo`s remain, and one open question if any.
5. Close: set the section's board status to `drafted`, update the Resume pointer,
   log nontrivial decisions, propose a commit
   (`draft(<section>): <one-line summary>`).

## Revision requests ("make the intro punchier", "shorten method by 20%")

Treat as a scoped edit of the same file: restate the instruction as you understood
it in one line, make surgical edits (no whole-section regeneration unless asked),
and show a brief before/after of the changed passages.
