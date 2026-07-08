---
name: paper-intake
description: >-
  Structured intake interview for an academic paper project (robotics/ML). Use
  whenever the author starts a new paper, says "start the intake", "new paper",
  "let's write up <project>", "interview me", or whenever state/interview.md is
  empty or thin and drafting is about to begin. Also use to run a focused
  mini-intake before drafting a specific section whose intent is not yet
  covered. The interview replaces ad-hoc prompt engineering: it is how the
  agent takes the initiative to fully understand the research, the author's line
  of thinking, and writing intent.
---

# Paper Intake Interview

Turn a finished research project into a written record of intent that every later
stage (outline, drafting, review, revision) can rely on, so the author never has to
re-explain the work and the agent never has to guess.

## Why this exists

Bad drafts almost always come from unstated intent, not bad writing. One interview
answer recorded now saves a full rewrite later. Treat the interview as the highest-
leverage activity in the whole pipeline and run it with care.

## Ground rules for the interview

1. **One question per turn.** Never batch questions. The author should be able to
   answer from a phone in one breath.
2. **Adapt, don't recite.** The question bank is a map, not a script. Skip what the
   author already answered (check `state/interview.md` and the conversation first),
   drill into vague answers ("robust" — robust to what, measured how?), and follow
   surprising answers with one follow-up before moving on.
3. **Record verbatim, immediately.** After each answer, append it to
   `state/interview.md` in the standard format (date, topic tag, Q, A) before asking
   the next question. Do not paraphrase away the author's wording — it is often the
   best wording for the paper.
4. **Checkpoint every ~8 questions.** Summarize what you have in 3 lines, ask whether
   to continue now or pause; if pausing, update the Resume pointer in
   `state/progress.md` so the interview resumes mid-phase next session.
5. **Never answer for the author.** If they say "you decide", propose an option, get
   explicit confirmation, and record it as their decision.

## Procedure

1. Read `state/project.md`, `state/interview.md`, `state/style.md`, and
   `evidence/results.md` to see what is already known. If the author's Obsidian
   vault is reachable (see "Linked knowledge" in `state/project.md`, or offer
   to connect it now), ask which idea note and literature MOC cover this
   project, read those selectively, and pre-fill candidate answers — then
   *confirm* each in the interview instead of asking cold, and record the note
   paths under Linked knowledge. Vault notes speed up elicitation; they never
   replace the author's confirmation.
2. Tell the author the plan: which phases you will cover (from
   `references/question-bank.md` — read it in full now) and roughly how many
   questions (a full intake is typically 20–35 questions, often split over 2–3
   sessions).
3. Run the interview phase by phase (A → H), following the ground rules above.
4. **Synthesize.** When phases A–F are covered:
   - Draft `state/project.md` (every field), quoting the author's own phrasing where
     it is strong.
   - **Transcribe author-provided results into `evidence/results.md`** —
     one E-row per result named in phases C–E, values verbatim (never
     rounded, derived, or extrapolated), with seeds/trials, uncertainty,
     and source fields filled from the author's answers. Missing numbers
     stay out: they become Open questions, not placeholder values. This
     table is drafting's ground truth; intake owns seeding it.
   - Update `state/style.md` with any preferences elicited in phase H.
   - List unresolved items under "Open questions" in `state/progress.md`.
5. **Read-back and confirm.** Open the synthesis message with a narrative
   read-back: 5–10 lines, in your own words, explaining what the research does,
   why it works, and what it claims — so the author can catch misunderstandings
   before any wording is polished. Then present the drafted project card for
   line-by-line confirmation. Contribution statements must be approved
   explicitly — they are the paper's spine. Drafting stays gated until this
   confirmation happens. The evidence table gets the same treatment as
   the contributions: the author confirms the transcribed rows before
   they are treated as frozen ground truth.
6. Close: update the section board and Resume pointer in `state/progress.md`, append
   a `decisions.md` entry ("intake completed; contributions fixed as C1–C3 because
   ..."), and propose a commit.

## Mini-intake variant

Before drafting a single section, run only the relevant phase (e.g., phase D–E for
Experiments) plus any open questions tagged for that section. Same ground rules;
usually 3–8 questions.
