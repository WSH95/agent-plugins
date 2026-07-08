---
name: paper-review-panel
description: Run a mock multi-reviewer peer review of the manuscript with independent reviewer personas and a meta-review synthesis. Use whenever the author says "review the paper", "mock review", "run the panel", "what would reviewers say", "red-team the paper", or before submission. Reviewer isolation rules here are mandatory — do not improvise a panel without this skill.
---

# Mock Review Panel

Simulate a program-committee review: five independent reviewers, then a meta-review
that synthesizes and prioritizes. Output lands in `state/reviews/round-N/`.

## Why isolation matters

Independent reviews are only informative if reviewers cannot anchor on each other or
on the authors' private knowledge. Two rules are therefore mandatory:
- Reviewers read **only `manuscript/`** — like real reviewers, they see the paper,
  not the lab notebook (`state/`, `evidence/` are off limits to them).
- No reviewer sees another review from the current round before finishing.
- Reviewers never receive the author's Obsidian vault or private reading
  notes; author interpretations of prior work reach the panel only through the
  verified, labeled briefing pack. A reviewer who has read the author's
  explanation of why the paper differs from prior work can no longer test
  whether the paper itself makes that case.

## Setup

1. Preconditions: the sections under review are at least `drafted` on the board.
   Ask which round this is; create `state/reviews/round-N/`.
2. The panel personas live in `.claude/agents/`: `reviewer-learning` (novelty &
   ablations), `reviewer-systems` (hardware & sim-to-real), `reviewer-theory`
   (formulation rigor), `reviewer-stats` (statistical methodology), and
   `reviewer-impact` (significance, archival completeness, broad-audience
   clarity — include for journal or high-impact targets such as T-RO and
   Science Robotics; optional for page-limited conferences). Offer to skip or
   add personas per the target venue.
3. Read the target venue from `state/project.md` and state it in every
   reviewer invocation as `Target venue: <venue>` — real reviewers know the
   venue, and each persona carries venue-calibration rules. Reviewers still
   never see `state/` itself.

## Path A — Claude Code (native subagents)

Invoke every reviewer subagent defined in `.claude/agents/` **in parallel,
in the same turn**, each with the prompt: "Review the paper in manuscript/ per
your instructions; output the full review." Each runs in a fresh isolated
context and returns its review as its final message. Save each verbatim to
`state/reviews/round-N/<reviewer-name>.md`.

## Path B — Codex (native subagent workflow)

Codex custom reviewer agents are defined in `.codex/agents/*.toml` (read-only
sandbox; they defer to the canonical `.claude/agents/*.md` personas). Codex
spawns subagents only when explicitly asked, so instruct it explicitly:
"Spawn one agent per reviewer — reviewer-learning, reviewer-systems,
reviewer-theory, reviewer-stats, reviewer-impact — wait for all of them, then
save each review verbatim to state/reviews/round-N/<name>.md." Isolation here is by
instruction and read-only sandbox, not by filesystem — note that in the
meta-review.

## Path C — scripted strict isolation (any CLI, strongest guarantee)

Run `BACKEND=claude scripts/review_panel.sh N` or `BACKEND=codex ...`. Each
persona runs as a separate non-interactive CLI call inside a temporary
directory containing **only a copy of `manuscript/`** — reviewers physically
cannot read `state/`, `evidence/`, or other reviews. Prefer this path for
final pre-submission panels.

Last-resort fallback (no CLI available, single context — say so in the
meta-review): for each persona **sequentially**, read only that persona file
and `manuscript/`, adopt the persona fully, write the review to its file, and
do not re-read reviews already written this round.

## Optional: briefed panel

Default panels are blind, like real review: reviewers know only what the model
already knows plus the paper. If the author wants reviewers to *reliably* know
the closest prior work (e.g., very recent competitors), enable the briefing
pack: the `paper-related-work` skill writes source-verified one-pagers to
`state/related-work/briefs/`, and the panel provides them — Path C via
`BRIEFING=1`, Paths A/B by adding "also read state/related-work/briefs/ (and
nothing else outside manuscript/)" to each invocation. Briefed reviews and
their meta-review must be labeled "briefed" so they are never mistaken for a
blind panel.

## Optional: evidence-aware internal review

Only if the author explicitly asks for an *internal* audit (not a venue
simulation), reviewers may additionally read `evidence/` to check
manuscript-vs-evidence consistency. Label such reports "internal audit — not
blind" so they are never confused with venue-style reviews.

## Meta-review (main agent, after all reviews exist)

Read all round-N reviews plus `state/project.md` and `evidence/results.md` (the
meta-reviewer, unlike reviewers, may check claims against the evidence base) and
write `state/reviews/round-N/meta-review.md`:

```
# Meta-Review — round N (date)
## Score summary
| Reviewer | Nov | Sound | Clar | Sig | Conf | Rec |
## Consensus strengths (deduplicated)
## Consensus weaknesses (deduplicated, cross-referenced W-ids)
## Points of disagreement (and the meta-reviewer's read)
## Reality check (reviewer claims contradicted by evidence/ — real reviewers can be wrong too)
## Top 5 must-fix items before submission (ranked)
## Overall call: {accept | borderline | reject} at <venue>, one-paragraph justification
```

## Close

Add the round to the Review rounds table in `state/progress.md`, update the Resume
pointer ("start with paper-revise on round N"), propose a commit. Then offer to run
`paper-revise`.
