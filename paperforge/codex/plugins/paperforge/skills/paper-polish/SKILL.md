---
name: paper-polish
description: Polish, tighten, proofread, or line-edit manuscript text. Use whenever the author says "polish", "edit", "tighten", "shorten", "proofread", "improve the writing", "we're over the page limit", or before submission. Runs structured editing passes plus the deterministic consistency checker (scripts/check_paper.py). Not for adding content or new claims — that is drafting.
---

# Polish Pass

Improve prose quality without changing scientific content. Polishing never adds
claims, numbers, or citations; if a passage *needs* new content, stop and flag it
for `paper-draft-section` instead.

## Scope first

Confirm scope before editing: which files/sections, and which passes (below). "Polish
the paper" defaults to all drafted sections, passes 1–6. Record a word/line count
before and after.

## The passes (run in this order)

1. **Structure & argument.** Within each section: does paragraph order follow the
   outline? Does each paragraph open with its topic sentence and contain one idea?
   Fix by moving/splitting paragraphs; do not rewrite sentences yet.
2. **Clarity & flow.** Sentence level: active voice by default, subject–verb
   close together, one idea per sentence, resolve dangling "this/it", replace
   vague intensifiers with specifics. Then information flow: open each sentence
   with what the reader already knows and put the new information last, where the
   next sentence picks it up (given→new / end-focus); the join between two
   sentences is where readers lose the thread, so close it with an overlapping
   repeat, a `This`/`These`+noun pro-form, a semicolon, or a signal word.
   Guardrails, because these edits regress easily: do NOT add a connector to every
   sentence and do NOT mechanically insert "This shows / This suggests /
   Therefore"; always attach a noun to a leading `This`/`These`; near math, LaTeX
   macros, and method/dataset/system names, terminology consistency and technical
   precision win over flow — never reword a symbol or defined term for rhythm.
   Flow is reader navigation, not a licence to add words.
3. **Claim calibration.** Match every claim's strength to its evidence, using
   `references/claim-calibration.md` (the claim-strength ladder, causal-verb
   precision, and the statistical claim-word gates). Scope or hedge overreach down
   to what `evidence/results.md` / `state/project.md` support; restore earned
   strength to timid underclaims. This pass changes claim *strength* only — never
   rewrite strong, supported prose into vaguer or hedge-laden language, and add no
   evaluative/marketing words. Treat each reworded claim as a meaning-changing
   edit: show before → after and get author sign-off.
4. **Concision.** Target from the author (default: −10–15%, more under page
   pressure). Cut throat-clearing ("It is worth noting that"), redundant hedges,
   and repeated information; compress via nominalization removal. Never cut
   assumptions, caveats, or reproducibility details to save space without asking.
5. **Mechanical.** Run `python3 scripts/check_paper.py` from the repo root and fix
   every ERROR and each WARN (or justify leaving it). Re-run until clean. Then
   compile (`make pdf`) if LaTeX is available and fix build issues.
6. **Style-sheet sweep.** Enforce `state/style.md` item by item: terminology table,
   banned phrases, tense/person rules, number formatting. When a rule is missing
   for a case you hit, ask once, then add the ruling to `state/style.md`.

When this is a pre-submission polish (not a mid-draft pass), also verify the paper
**title** against the Title blueprint in `paper-draft-section`'s
`references/section-protocols.md`: flag overpromising, vague topic-only breadth,
opaque acronyms, compound-noun pileups, or mismatch with target-venue title norms.
Suggest fixes; the title is the author's call.

## Editing discipline

- Edit surgically per file; keep the author's voice — polish removes friction, it
  does not homogenize. If a sentence is unusual but clear and deliberate, leave it.
- For substantive rewordings (meaning could shift), show before → after pairs and
  get approval; for mechanical fixes, batch and summarize.
- Anything ambiguous about *meaning* is a question for the author, not an editorial
  guess.

## Close

Report: passes run, word-count delta, checker summary (errors/warnings/todos
remaining), and any style rulings added. Set affected sections to `polished` on the
board, update the Resume pointer, propose a commit (`polish(<scope>): <summary>`).
