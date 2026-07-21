---
name: paper-revise
description: Turn reviews (mock panel rounds or real venue reviews) into a prioritized revision plan, execute the writing-side fixes, and draft the author response / rebuttal. Use whenever the author says "revise", "address the reviews", "rebuttal", "response letter", "fix what the reviewers said", or after a paper-review-panel round completes.
---

# Revise and Respond

Convert a review round into (1) `revision-plan.md`, (2) executed manuscript edits for
agent-ownable items, and (3) a response letter when reviews are real.

## 1. Ingest

Read every review in `state/reviews/round-N/` plus `meta-review.md`. For real venue
reviews: save them verbatim into the same round structure first (one file per
reviewer) so the pipeline is identical, then offer to run the area-chair
adjudication over them (the `area-chair` persona from `paper-review-panel` —
same pipeline), which yields evidence-checked verdicts and ready rebuttal
material. Once `meta-review.md` exists, run `python3 scripts/check_reviews.py N`
(mock rounds: re-run it here as a cheap gate). If the author declines the
adjudication, skip the checker and plan from the raw reviews.

## 2. Plan — `state/reviews/round-N/revision-plan.md`

One row per distinct review point (merge duplicates across reviewers, keep W-id
cross-references):

| ID | Point (short) | Reviewers | Priority | Owner | Action | Section |

- Priority: **P0** must fix before submission / rebuttal; **P1** should fix;
  **P2** optional or explicitly rebut.
- Owner: **agent** (writing/positioning/clarity fix), **author** (needs a new
  experiment, a decision, or domain judgment), or **discuss** (the point may be
  wrong — check against `evidence/` and `state/project.md`; reviewers can be
  mistaken, and the correct response is a respectful, evidence-backed rebuttal,
  not a concession).
- When the meta-review carries an Adjudication table, seed Priority and Owner
  from its verdicts: `confirmed` majors → P0/P1 (follow the area chair's
  top-5 ranking); `partly-confirmed` → P1 with a note narrowing the scope;
  `refuted` → P2 with Owner `discuss` and the area chair's evidence pointer
  prefilled in Action (a refuted point is rebuttal material — never silently
  drop the row); `judgment-call` → `author` or `discuss` weighted by how many
  reviewers raised it; `out-of-scope` → P2 with a venue note.

Copy every item under the meta-review's "Points for the author" into Open
questions in `state/progress.md` — those are the area chair's contested calls,
and the author is the final arbiter. Walk the plan with the author and get
sign-off before editing anything. Author-owned items go under Open questions
in `state/progress.md` with what is needed.

## 3. Execute (agent-owned items)

Work section by section, P0 first, using the `paper-draft-section` editing
discipline (surgical diffs, grounding gates, one section per pass). Tick items in
the plan as done with a one-line note of what changed. Re-run
`python3 scripts/check_paper.py` after the batch.

## 4. Response letter (real reviews; optional for mock rounds)

Write `state/reviews/round-N/response.md`, grouped by reviewer, quoting each comment
followed by the response:

- Structure: thank → answer directly → state the change and *where*
  ("Revised in Sec. IV-B, para. 2") → evidence if applicable.
- Tone: professional, non-defensive, specific. Concede real points plainly;
  rebut wrong ones with evidence, never with volume.
- When rebutting a point the meta-review refuted, cite the area chair's
  evidence pointer (Sec./Fig./E#) — rebut with the located evidence, not
  with restated opinion.
- Never claim a change that was not actually made — cross-check every "we have
  revised" against the diff.

## 5. Close

Update the Review rounds table and Resume pointer, set touched sections to
`revised`, append a `decisions.md` entry for any claim/scope changes forced by the
round, propose a commit (`revise(round-N): <summary>`). Offer a follow-up panel
round to verify the fixes landed.
