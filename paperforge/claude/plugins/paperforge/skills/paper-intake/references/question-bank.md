# Intake Question Bank

A map of what must be known before writing. Core questions are asked almost always;
follow-ups fire when the trigger condition holds. Adapt wording to the project —
the examples are robotics/RL-flavored but the structure is general.

## Phase A — Problem and motivation
- A1. In one or two sentences, what problem does this work solve?
- A2. Why is it hard? What breaks when the obvious approach is tried?
- A3. Who cares — what becomes possible if this is solved? (application pull vs.
  scientific push)
- Follow-up (if the answer is a method, not a problem): "That's the solution — what
  is the problem it answers?"

## Phase B — Contribution and novelty
- B1. List the contributions as you would defend them to a hostile reviewer
  (aim for 2–4).
- B2. For each: what is the *closest* prior work, and what exactly is the delta —
  new capability, new formulation, new evidence, or new system?
- B3. Which existing paper worries you most as an overlap threat? What would you say
  to a reviewer who cites it against you? (Record the answer carefully — it becomes
  a Related Work paragraph and a rebuttal draft.)
- B4. If you could only keep one contribution, which one? (Determines the paper's
  spine and the abstract's emphasis.)
- Follow-up (if a contribution is an engineering detail): "Is this a contribution or
  an implementation choice? What claim does it support?"

## Phase C — Method essentials
- C1. Walk me through the method at whiteboard level: inputs, outputs, training
  signal, what is learned vs. designed.
- C2. What is the *key idea* — the one design decision that makes it work — and what
  is the intuition for why?
- C3. Which formulation choices need justification (e.g., POMDP vs. MDP, asymmetric
  actor–critic, factored actions), and what is the justification?
- C4. What did you try that failed? (Failed attempts often justify the final design
  and preempt "why not simply..." reviews.)

## Phase D — Experiments inventory
- D1. Platforms and environments: which robots, which simulators, which terrains/tasks?
- D2. Baselines: which are implemented, which are numbers taken from papers, and is
  the comparison protocol identical?
- D3. Metrics and seeds: what is measured, how many seeds/trials, what uncertainty
  is reported? (Default standard: rliable — IQM + stratified bootstrap CIs.)
- D4. Ablations: which components have isolating ablations? Any missing?
- D5. What exists already in `evidence/` vs. what is still planned? (Only existing
  results may be drafted as results.)

## Phase E — Results and story
- E1. What is the headline result — the single finding the abstract leads with?
- E2. What surprised you in the results? (Surprises make discussion sections.)
- E3. Any negative or mixed results? How honest do you want the paper to be about
  them? (Recommend: fully — reviewers reward it.)
- E4. What are the real limitations, stated in your own words?

## Phase F — Venue, type, and framing
- F1. Target venue and deadline? Page limit? (Verify the current CFP rather than
  assuming.)
- F2. Paper type/character — empirical evaluation, systems, methods-heavy, or
  theory? (Shapes section emphasis and architecture. Survey / position / resource
  papers fall outside this kit's evidence-grounded model.)
- F3. Intended article structure — conference short paper or journal full paper; a
  separate Discussion, a combined Results-and-Discussion, or interpretation folded
  into Experiments; a short or an expanded Conclusion/Limitations? The author may
  defer this to `paper-outline`, which confirms the section architecture (and can
  profile recent target-venue articles to infer current norms). Both conference and
  journal papers are first-class — there is no default structure.
- F4. What does *this* venue's audience value most — hardware demos, statistical
  rigor, theoretical framing? How should emphasis shift accordingly?
- F5. Any co-author constraints (sections owned by others, advisor preferences)?

## Phase G — Figures and tables
- G1. Inventory: which figures/plots already exist, which are planned?
- G2. What should the teaser (Fig. 1) communicate in three seconds?
- G3. Any video/website companion planned?

## Phase H — Writing preferences (feeds state/style.md)
- H1. Papers whose *writing* you admire and want to emulate? What specifically about
  them?
- H2. Pet peeves — words, phrasings, or structures you never want to see?
- H3. Density preference: math-forward or prose-forward method section?
- H4. Anything about tense, person, hyphenation, or terminology to fix now?

## Closing question (always)
- Z1. "What have I not asked about that a reader must understand for this paper to
  make sense?"
