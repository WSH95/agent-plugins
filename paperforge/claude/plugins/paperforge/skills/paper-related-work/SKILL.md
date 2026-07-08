---
name: paper-related-work
description: Build the related-work section and the citation base. Use whenever the author says "related work", "literature", "positioning", "find citations", "what should we cite", or when Sec. II needs drafting or updating. Enforces verified-citations-only discipline (no citing from memory) and delta-sentence positioning.
---

# Related Work

Produce three artifacts: `state/related-work-map.md` (the positioning table),
`manuscript/sections/2_related_work.tex`, and a synchronized `manuscript/refs.bib`.

## The one hard rule

**Never cite from memory alone.** A fabricated or mis-attributed citation is the
single most damaging error this pipeline can produce. Every entry must be verified
against a live source before it enters `refs.bib`. Source priority:
1. The author's Zotero library (via Zotero MCP / Better BibTeX export) — canonical.
2. arXiv / alphaXiv MCP or a fetched abstract page.
3. Web search to the publisher/arXiv page.
4. If none of these tools are available in this session: collect the *claims that
   need support* as `\todo{CITE: ...}` markers and give the author a lookup list —
   do not fill in guessed references.

If a paper "should exist" but cannot be verified, it does not exist for our purposes.

**Discovery aid (not a verification source): the author's Obsidian vault.**
When reachable (see "Linked knowledge" in `state/project.md`), search the
designated literature notes first — they are the fastest route to candidate
works, the author's own delta language, and the papers that worry them. Every
candidate found this way still climbs the verification ladder above before
entering `refs.bib`, and no prose is copied from notes: literature notes often
embed verbatim excerpts from the papers themselves.

## Procedure

1. **Themes.** Derive 3–5 themes from the claims map in `state/outline.md` /
   `state/project.md`. Each theme exists to position a contribution; a theme that
   positions nothing gets cut.
2. **Gather.** For each theme, collect candidate works via the source priority
   above. Include, non-negotiably, every overlap-threat paper from interview B3.
3. **Map.** Write/update `state/related-work-map.md`:

   | Theme | Work (bib key) | Venue, year | What it does (1 line) | Our delta (1 line) |

   Deltas must be specific ("assumes full state; we operate from onboard vision"),
   not generic ("we are different").
4. **Sync refs.bib.** Add verified entries; prefer official BibTeX from the
   publisher/arXiv over hand-written entries; keep keys in `author-year-keyword`
   style consistently.
5. **Draft.** One paragraph per theme; group works by what they do; end each
   paragraph with the delta sentence. Tone: respectful and accurate — reviewers are
   often the people being cited, and mischaracterizing a work is both wrong and
   dangerous.
6. **Audit.** Grep every `\cite` in the section against `refs.bib`; confirm every
   map row is either cited or consciously dropped.
7. **Close.** Board status, Resume pointer, `decisions.md` entry for any positioning
   decision (e.g., which threat paper is addressed head-on in the intro instead),
   propose a commit.

## Briefing pack (feeds the review panel's briefed mode)

On request — or proactively for the overlap-threat papers from interview B3 —
write a one-page brief per key work to `state/related-work/briefs/<bibkey>.md`:
citation and link at the top, then the work's claim, method essence, headline
evidence, and the explicit delta versus ours. Build briefs ONLY from verified
sources (fetched paper or abstract via Zotero/arXiv MCP or the web), quoting
at most a short phrase; a brief that cannot be source-verified is not written.
Vault notes may suggest *which* works need briefs and *what matters* about
them, but every factual line in a brief is re-verified against the fetched
source. These double as rebuttal preparation.

## Maintenance mode

When new relevant work appears mid-project ("reviewer will know about X", "a new
arXiv paper came out"), verify it, add a map row, and patch the affected paragraph —
do not rebuild the section.
