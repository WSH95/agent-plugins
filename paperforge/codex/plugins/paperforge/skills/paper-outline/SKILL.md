---
name: paper-outline
description: Build the paper outline as a claims-to-evidence-to-sections map. Use whenever the author says "outline", "structure the paper", "plan the sections", after the intake interview completes, or before any section drafting when state/outline.md does not exist. Drafting without this outline is the main cause of structural rewrites, so trigger eagerly.
---

# Paper Outline

Produce `state/outline.md`: a paragraph-level plan in which every paragraph exists to
advance a claim, and every claim points at its evidence. The outline is cheap to
change; drafted prose is not — so all structural argument happens here.

## Preconditions

- `state/project.md` has confirmed contributions. If not, run `paper-intake` first.
- The target venue and paper type are recorded in `state/project.md` (from
  intake). They set the section architecture (step 1); if missing, confirm them
  before budgeting.
- `evidence/results.md` lists the existing results. Read it: the outline may only
  promise evidence that exists or is explicitly marked planned.

## Procedure

1. **Section architecture.** Before budgeting, confirm the paper's structure from
   the venue/paper-type profile in `state/project.md` (see "Section architecture"
   in the `paper-draft-section` skill's `references/section-protocols.md`):
   conference short paper, journal full paper, separate Discussion, combined
   Results-and-Discussion, and the ending style (short Conclusion vs expanded
   Conclusion/Limitations). There is no default — choose from venue norms, paper
   type, results complexity, and page budget, and record the choice in
   `state/project.md` (its Paper type and Section architecture fields).

   *Optional — target-venue norm profiling.* When the norms are unclear, analyze
   3–4 recent articles from the exact target venue to observe their **structure**:
   section architecture, typical length, subsection patterns, citation density,
   abstract/title conventions, appendix/supplement use. Record the observations in
   `state/project.md`. Hard rules: **verified sources only** (author's library,
   arXiv/publisher pages, or a fetched article — the `paper-related-work` source
   ladder); observe **structure, not prose** — never copy phrasing; never treat a
   target article as a factual or citable source. If you cannot reach reliable
   samples (no library / MCP / web access), **say so** and fall back to the
   author's stated venue constraints and the venue notes — do not invent a norm.
2. **Page budget.** From the venue, page limit, and chosen architecture in
   `state/project.md`, propose a per-section budget. E.g. a 6-page conference
   paper: Intro 0.9, Related 0.6, Method 1.8, Experiments 1.9, Conclusion 0.3
   (figures included); a journal paper additionally budgets a Results/Discussion
   split and a fuller Related Work. State the assumption and let the author adjust.
3. **Claims map.** Table: each contribution C1..Cn → the sections/figures/tables that
   establish it → the evidence rows backing those. Flag any claim with no evidence
   (drop the claim or mark the experiment as required — author decides; log it).
4. **Paragraph plan.** For each section in the chosen architecture, list paragraphs
   as one-line *topic sentences* (assertions, not topics: "Blind policies fail on X
   because Y", not "Discussion of blind policies"). Attach evidence pointers and
   figure callouts. Follow the per-section blueprints in the `paper-draft-section`
   skill's `references/section-protocols.md`. (Cross-skill dependency: this skill
   assumes `paper-draft-section` is installed alongside it — the seven kit skills
   ship as a set; if the blueprints file is missing, say so and fall back to the
   default order in step 7 rather than improvising blueprints.)
5. **Confirm.** Walk the author through the outline top-to-bottom. Contribution
   ordering, experiment ordering, and what gets cut under page pressure are author
   decisions — surface them explicitly.
6. **Scaffold.** On approval, realize the chosen architecture in
   `manuscript/sections/`. The shipped skeleton is a **journal-superset** seed
   (`4_results`, `5_discussion`, `6_conclusion` = Conclusion and Limitations). For
   a **conference short paper**, merge Results+Discussion into a single Experiments
   section and drop `5_discussion` and its `\input` in `main.tex`; for a **combined
   Results-and-Discussion**, keep one interpreting section. Then write the topic
   sentences into the `*.tex` files as `%` comments above `\todo{}` placeholders so
   drafting fills a fixed structure. Record any files added, removed, or renamed in
   `decisions.md`.
7. **Close.** Set the section board to `outlined` and fill its Next-action column
   following the profile's drafting order (see the draft skill's
   `references/section-protocols.md`; Discussion slots in after Results/Experiments
   for profiles that have one). Point the Resume pointer at the first section,
   append a `decisions.md` entry, propose a commit.

## Output format of state/outline.md

```
# Outline (venue, paper type, architecture, page limit, date)
## Page budget
## Claims map
| Claim | Established in | Evidence |
## Section plans
### 1 Introduction (target: X.X pages)
- P1: <topic sentence> [evidence/figure pointer]
- P2: ...
```
