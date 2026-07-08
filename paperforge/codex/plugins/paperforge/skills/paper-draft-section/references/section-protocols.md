# Section Blueprints

Read only the part for the section being drafted.

## Contents
- [Section architecture (choose the mode first)](#section-architecture-choose-the-mode-first)
- [Recommended drafting order](#recommended-drafting-order)
- [Title](#title)
- [Abstract](#abstract)
- [Introduction](#introduction)
- [Related Work](#related-work)
- [Method](#method)
- [Experiments](#experiments)
- [Discussion](#discussion)
- [Conclusion and Limitations](#conclusion-and-limitations)
- [Venue notes](#venue-notes)

## Section architecture (choose the mode first)

There is no default paper structure. `paper-outline` confirms the **section
architecture** from the venue/paper-type profile in `state/project.md` before any
drafting; these blueprints are the menu it draws from. Common modes:

- **Conference short paper** (ICRA / IROS / CoRL / RSS / NeurIPS-style): Intro,
  Related Work, Method, Experiments, short Conclusion. Interpretation lives inside
  Experiments; usually no separate Discussion. Tight page budget.
- **Journal full paper** (T-RO / RA-L-style): fuller Related Work and Method, a
  Results section and often a **separate Discussion**, an expanded
  Conclusion/Limitations. Archival completeness over compression.
- **Combined Results and Discussion**: one section interprets each result set in
  place — common when later results depend on reading the earlier ones.
- **Significance-first** (Science Robotics-style): Results/Discussion before
  Materials and Methods, general-audience abstract; see Venue notes.

Pick per venue norms, paper type, results complexity, and page budget — not by
habit. A conference paper is not the default, and a journal paper is not forced
into full IMRD. Whichever mode is chosen, the grounding rules and these
per-section blueprints apply unchanged.

The scaffolded manuscript ships **journal-shaped** (Results + Discussion +
Conclusion/Limitations); `paper-outline` trims it for a conference paper (merge
Results+Discussion into one Experiments section, drop the separate Discussion), so
the shipped seed and these modes agree.

## Recommended drafting order

Order is profile-dependent (the author may override; record overrides in
`decisions.md`). A good default:
1. **Method** — the most settled content; drafting it first stabilizes notation
   and structure for everything else.
2. **Experiments / Results** — written directly against `evidence/results.md`
   while the results are fresh.
3. **Discussion** — *only in profiles that have one* (journal / separate-Discussion);
   draft it after Results, once the findings are on the page. In a combined
   Results-and-Discussion mode, interpretation is drafted with each result set
   instead of as its own pass.
4. **Related Work** — positioning is sharper once method and results text exist.
5. **Introduction** — written after the body, when it is clear exactly what is
   being introduced.
6. **Conclusion and Limitations.**
7. **Abstract, then Title** — always last, compressed from finished sections.

Loop per section: draft → present with delta summary → author feedback →
surgical revisions → author confirms → board status `drafted`, then move on.
Defer deep line-editing to a whole-paper `paper-polish` pass, so later structural
changes do not waste earlier polish work.

## Title

The title is the paper's most-read line and its entry point. Aim: expose the
paper's specific, evidence-bounded promise and be readable and discoverable. This
is a checklist of failure modes to avoid, **not** a required format — a title
named after the method, system, problem, benchmark, or a defined acronym is fine
when it fits venue norms and does not promise more than the paper delivers.

Flag (and offer a fix for) a title that:
- **Overpromises** — claims a result, generality, or capability the paper does not
  support. The title passes the same claim calibration as the abstract.
- **Is a vague topic label** — names only the area ("… in pipe networks") instead
  of what the paper contributes or does.
- **Hides behind an opaque acronym** — unreadable to a near-adjacent or future
  reader; spell it out or move it into the body unless it is genuinely standard at
  the target venue.
- **Piles up compound nouns** — a long noun chain whose relations the reader must
  untangle; break it or move modifiers into the keyword list.
- **Turns on an ambiguous preposition** — where "for / with / in / of" could attach
  two ways; reword to a form with a single reading.
- **Buries the discoverable keywords** — the terms a target reader would search for
  should be present and near the front.
- **Mismatches venue title norms** — length, sentence-vs-noun-phrase form, colon
  use; check recent titles in the target venue (see Venue notes).

Draft or verify the title with the abstract (both come last). Suggest; the title
is the author's call.

## Abstract

Write it **last**, from finished sections. Four moves, ~150–200 words total:
1. Context + problem (1–2 sentences): the problem and why it matters/is hard.
2. Gap (1 sentence): what existing approaches cannot do.
3. Approach (2–3 sentences): the key idea, named (if the method has a name) —
   mechanism, not a component list.
4. Results (1–2 sentences): the headline result **with the number** from
   `evidence/results.md`, plus scope (platform, tasks).
No citations, no undefined acronyms, no "in this paper we". Draft or verify the
**Title** together with the abstract — both are written last (see the Title
blueprint above).

## Introduction

Paragraph blueprint (adjust count to the page budget):
- P1 Context: the capability the field wants; concrete, not grandiose.
- P2 Problem + why hard: the specific technical obstacle.
- P3 Prior-work limitation: what the closest approaches do and where they stop.
  One or two citation clusters, not a survey (that is Sec. II's job).
- P4 Key idea: "Our key insight/observation is ..." — the single idea from
  interview C2, stated so a reader could almost reinvent the method.
- P5 Contributions: bulleted, copied in substance from `state/project.md`
  (wording may be polished; claims may not drift).
- P6 (optional) Results preview: one headline number + platform.
The teaser figure (Fig. 1) is referenced from P1 or P4.

## Related Work

Prefer the dedicated `paper-related-work` skill. Core rules if drafting here:
one paragraph per theme (3–5 themes from the claims map); within a paragraph,
group works by what they *do*, not chronologically; **end every paragraph with an
explicit delta sentence** ("Unlike these, we ..."). Cover the overlap-threat papers
from interview B3 head-on — omission reads as either ignorance or evasion.

## Method

- Open with the problem formulation: state the decision problem precisely
  (e.g., POMDP tuple, observation/state split, objective) using `macros.tex`
  symbols only. The formulation must match what the algorithm actually observes
  and optimizes — reviewers check this.
- State assumptions where they are used, not in a pile at the end.
- Order subsections by the reader's dependency graph (what must be understood
  first), not by implementation chronology.
- For each design choice flagged in interview C3: choice → alternative → reason.
  One sentence each is enough; silent choices attract "why not X?" reviews.
- Every equation earns its place: if removing it loses nothing, remove it.
  Every symbol is defined at first use.
- Implementation detail policy: enough to reproduce (architecture sizes, key
  hyperparameters, training budget) in the main text or an explicit appendix
  pointer — decide per venue page pressure and record in `decisions.md`.

## Experiments

- Open with explicit experimental questions: "Our experiments answer: (EQ1) ...,
  (EQ2) ..., (EQ3) ...". Each EQ maps to a claim in `state/project.md`; each
  subsection answers one EQ and *says so* in its first sentence.
- Setup subsection: platforms, simulators, tasks, baselines (and whether baseline
  numbers are re-run or quoted), metrics, seeds, protocol. Identical-protocol
  statement for comparisons.
- Reporting standard (default rliable; see `evidence/results.md`): IQM or median
  with stratified bootstrap CIs, seed counts stated, performance profiles for
  multi-task comparisons. Do not write "significantly" without a test or
  non-overlapping CIs.
- Every table/figure is called out in prose and interpreted in one or two
  sentences — what the reader should conclude, not a restatement of the numbers.
- Include failure modes / qualitative analysis where interview E2–E3 provides
  material; honest negatives buy reviewer trust.

## Discussion

Present **only** when the section architecture calls for it (journal full paper, or
a combined Results-and-Discussion mode) — conference short papers usually fold
interpretation into Experiments and omit it. The Discussion **interprets**; it does
not re-report. Core roles: say what the results *mean*, bound their generality,
connect them to verified literature, and surface limitations and failure modes. It
mirrors the Introduction in reverse — the Intro narrows from the field to this
work; the Discussion widens from this work back out.

Grounding boundaries (non-negotiable, same as everywhere):
- Introduce **no** new numbers, no unverified citations, and no claim not grounded
  in `state/project.md` / `evidence/results.md`.
- It does not compensate for weak Results — if the finding is thin, the Discussion
  cannot argue it stronger.
- Keep the register separable and calibrated (see the `paper-polish` skill's
  `references/claim-calibration.md`): **observation** (already in Results) →
  **interpretation** → **implication** → **limitation** → **speculation** (labeled,
  and never in the abstract).

Blueprint (order is flexible; not every item every time):
- Open by revisiting the gap/aim or the headline result, then state how far this
  work resolves it — the reverse of the Intro's move into the work.
- Interpret the key results: what they mean and why they came out this way, at the
  causal strength the evidence licenses (an ablation, not a guess).
- Map to the literature: how the findings confirm, extend, or contradict verified
  prior work; position the contribution on the research map.
- Bound generality: the conditions, tasks, and regimes where the claims hold.
- Limitations and failure modes: concrete and specific (from interview E4); honest
  negatives buy reviewer trust.
- Implications / future directions that follow from the limitations.

**Separate Discussion vs Conclusion:** place Discussion after Results/Experiments
and before Conclusion; the Conclusion then stays short (below) and does **not**
repeat the full interpretation — Discussion interprets and bounds the findings,
Conclusion closes the contribution and names next steps.

**Combined Results-and-Discussion:** interpret each result set locally, in its own
subsection, right after presenting it; do not repeat that interpretation later.
Keep observation and interpretation distinguishable within the subsection (state
the number, then read it). This differs from the ML **Experiments** blueprint only
in emphasis — Experiments answers EQ-by-EQ against claims; a combined
Results-and-Discussion additionally develops the interpretation in place. Choose
one home for interpretation; do not run both.

## Conclusion and Limitations

Ending style follows the section architecture:
- **Short Conclusion-only** (conference, or when a separate Discussion already
  carries the interpretation and limitations): one tight paragraph — what was
  shown and the single most important next step. Do not restate the Discussion.
- **Expanded Conclusion/Limitations** (journal without a separate Discussion, or
  when limitations belong here): the fuller form below.

- 1 paragraph: restate what was shown (past tense, no new claims, no new numbers).
- Limitations: concrete and specific (from interview E4) — name conditions where
  the method degrades. Vague limitations ("more experiments needed") read as
  evasive. If a separate Discussion already carries limitations, do not duplicate
  them here.
- Future work: at most 2–3 directions that follow from the limitations.

## Venue notes

Approximate norms — **verify the current CFP before relying on page counts**, and
note that these drift year to year. When it matters, `paper-outline` can profile
the **current** norms (section architecture, length, citation density,
abstract/title conventions, appendix use) by analyzing a few recent articles from
the target venue — observed structure only, never their prose, verified sources
only. Fall back to the notes below when that is unavailable:
- ICRA / IROS: ~6 pages + references; hardware evidence and video weigh heavily;
  IEEEtran two-column tightness — budget figures carefully.
- RA-L: journal-style rigor, ~8 pages; reproducibility details expected.
- CoRL: ~8 pages + appendix; learning novelty and thorough ablations; appendix is
  read, so overflow details go there rather than being cut.
- RSS: formulation rigor and depth valued; fewer, deeper experiments acceptable.
- NeurIPS / ICLR: statistical rigor (rliable norms), broader-ML positioning,
  checklist compliance (limitations, compute, reproducibility statements).
- T-RO: archival journal depth — thorough related work, complete implementation
  detail, and experiments that close the loop on every claim; expect multi-round
  revisions with detailed response letters (the `paper-revise` skill's format);
  current norms at https://www.ieee-ras.org/publications/t-ro.
- Science Robotics: significance-first with editorial triage before review;
  AAAS article structure (Results and Discussion before Materials and Methods,
  methods at the end), a general-audience abstract, and figure/video-driven
  evidence; restructure rather than reformat — check the current author
  guidelines via https://www.science.org/journal/scirobotics.
