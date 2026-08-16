---
name: paper-review-panel
description: Run a mock multi-reviewer peer review of the manuscript with independent reviewer personas and an independent area-chair adjudication (the meta-review). Use whenever the author says "review the paper", "mock review", "run the panel", "what would reviewers say", "red-team the paper", or before submission. Reviewer isolation rules here are mandatory — do not improvise a panel without this skill.
---

# Mock Review Panel

Simulate a program-committee review: five independent reviewers, then an
independent area-chair adjudication (the meta-review) that rules on every
major weakness with evidence and prioritizes. Output lands in
`state/reviews/round-N/`.

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
2. The five panel personas are the `reviewer-*` files in `.claude/agents/`:
   `reviewer-learning` (novelty &
   ablations), `reviewer-systems` (hardware & sim-to-real), `reviewer-theory`
   (formulation rigor), `reviewer-stats` (statistical methodology), and
   `reviewer-impact` (significance, archival completeness, broad-audience
   clarity — include for journal or high-impact targets such as T-RO and
   Science Robotics; optional for page-limited conferences). Offer to skip or
   add personas per the target venue. The `area-chair` persona also lives
   there, but it is the meta-review adjudicator — never a panel reviewer.
3. Read the target venue from `state/project.md` and state it in every
   reviewer invocation as `Target venue: <venue>` — real reviewers know the
   venue, and each persona carries venue-calibration rules. Reviewers still
   never see `state/` itself.

## Path A — native project agents (Claude Code and Grok Build)

Both Claude Code and Grok Build discover the `reviewer-*` files in
`.claude/agents/` as project agents. Invoke every `reviewer-*` **in
parallel, in the same turn**, each with the prompt: "Review the paper in
manuscript/ per your instructions; output the full review." On Grok Build
that is `spawn_subagent` with `subagent_type` set to the persona name
(`reviewer-learning`, `reviewer-systems`, `reviewer-theory`,
`reviewer-stats`, `reviewer-impact`) and `capability_mode: read-only`.
Each runs in a fresh isolated context and returns its review as its final
message. Save each verbatim to `state/reviews/round-N/<reviewer-name>.md`.

## Path B — Codex (native subagent workflow)

Codex custom reviewer agents are defined in `.codex/agents/reviewer-*.toml`
(read-only sandbox; they defer to the canonical `.claude/agents/*.md`
personas). Codex
spawns subagents only when explicitly asked, so instruct it explicitly:
"Spawn one agent per reviewer — reviewer-learning, reviewer-systems,
reviewer-theory, reviewer-stats, reviewer-impact — wait for all of them, then
save each review verbatim to state/reviews/round-N/<name>.md." Isolation here is by
instruction and read-only sandbox, not by filesystem — pass that caveat to
the area chair when you invoke the meta-review step.

## Path C — scripted strict isolation (any CLI, strongest guarantee)

Run `BACKEND=claude scripts/review_panel.sh N`, `BACKEND=codex ...`, or
`BACKEND=grok ...`. Each
persona runs as a separate non-interactive CLI call inside a temporary
directory containing **only a copy of `manuscript/`** — reviewers physically
cannot read `state/`, `evidence/`, or other reviews. Prefer this path for
final pre-submission panels.

Last-resort fallback (no CLI available, single context — say so in the
meta-review): for each persona **sequentially**, read only that persona file
and `manuscript/`, adopt the persona fully, write the review to its file, and
do not re-read reviews already written this round. Run the area-chair
protocol afterwards in this same context (see the meta-review section); its
output must carry the `non-independent (main agent)` label on the `Panel:`
line.

## Optional: briefed panel

Default panels are blind, like real review: reviewers know only what the model
already knows plus the paper. If the author wants reviewers to *reliably* know
the closest prior work (e.g., very recent competitors), enable the briefing
pack: the `paper-related-work` skill writes source-verified one-pagers to
`state/related-work/briefs/`, and the panel provides them — Path C via
`BRIEFING=1`, Paths A/B by adding "also read state/related-work/briefs/ (and
nothing else outside manuscript/)" to each invocation. Briefed reviews and
their meta-review must be labeled "briefed" so they are never mistaken for a
blind panel; pass the label to the area chair too — only then may it read
`state/related-work/briefs/`.

## Optional: evidence-aware internal review

Only if the author explicitly asks for an *internal* audit (not a venue
simulation), reviewers may additionally read `evidence/` to check
manuscript-vs-evidence consistency. Label such reports "internal audit — not
blind" so they are never confused with venue-style reviews, and pass the
label to the area chair for the meta-review header.

## Meta-review — area-chair adjudication (fresh subagent, after all reviews exist)

The meta-review is written by the `area-chair` persona in a fresh context —
never by this session, which drafted the paper and cannot judge it
independently.

1. Invoke the `area-chair` subagent (Claude Code or Grok Build: the
   `area-chair` project agent from `.claude/agents/`; on Grok,
   `spawn_subagent` with `subagent_type: area-chair`. Codex: "Spawn the
   area-chair agent"), passing the round number, which path produced the
   reviews plus its isolation caveats, and any briefed / internal-audit
   labels. It reads the manuscript first, then the round's reviews,
   `evidence/results.md`, and `state/project.md`, and rules on every
   major weakness with an evidence-cited verdict (`confirmed |
   partly-confirmed | refuted | judgment-call | out-of-scope`).
2. Save the returned meta-review **verbatim** to
   `state/reviews/round-N/meta-review.md`. Do not write or edit meta-review
   content yourself; if something looks wrong, re-invoke the area chair —
   never patch its ruling silently.
3. Run `python3 scripts/check_reviews.py N`. On failure, re-invoke the area
   chair with the checker's failure list and save the corrected output.

No-subagent fallback: run the same protocol in this context — read
`.claude/agents/area-chair.md` and follow it exactly — and label the
meta-review `non-independent (main agent)` on its `Panel:` line.

```
# Meta-Review — round N (date)
Panel: {path and isolation caveats — plus briefed / internal-audit / non-independent labels when they apply}

## Score summary
| Reviewer | Nov | Sound | Clar | Sig | Conf | Rec |

## Adjudication of major weaknesses
| W-id | Reviewer | Verdict | Evidence (Sec./Fig./E#) | Note |
| W1 | reviewer-learning | confirmed | Sec. IV-B / E3 | one-line note |

## Consensus strengths (deduplicated)

## Consensus weaknesses (deduplicated, cross-referenced W-ids)

## Points of disagreement (and the area chair's read)

## Reality check (reviewer claims contradicted by the manuscript or evidence/ — real reviewers can be wrong too)

## Points for the author (contested verdicts + judgment calls needing a human decision)

## Top 5 must-fix items before submission (ranked)

## Overall call: {accept | borderline | reject} at <venue>, one-paragraph justification
```

## Close

Add the round to the Review rounds table in `state/progress.md`, update the Resume
pointer ("start with paper-revise on round N"), propose a commit. Then offer to run
`paper-revise`.
