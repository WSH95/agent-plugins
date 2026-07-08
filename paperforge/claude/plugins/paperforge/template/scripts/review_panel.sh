#!/usr/bin/env bash
# Run the mock review panel with FILESYSTEM-ENFORCED reviewer isolation.
#
# Each reviewer runs as a separate non-interactive CLI call inside a fresh
# temporary directory that contains ONLY a copy of manuscript/ — so reviewers
# physically cannot read state/, evidence/, or other reviews, regardless of
# tool flags or prompt compliance. This is the strict-isolation path; inside
# Claude Code or Codex you can instead let the paper-review-panel skill spawn
# native subagents (convenient, isolation-by-instruction).
#
# Usage (from the repository root):
#   BACKEND=claude scripts/review_panel.sh 1     # round 1 via `claude -p`
#   BACKEND=codex  scripts/review_panel.sh 2     # round 2 via `codex exec`
#   BRIEFING=1 BACKEND=claude scripts/review_panel.sh 3
#       # briefed panel: also copies state/related-work/briefs/ (source-verified
#       # one-pagers on the closest prior work) into each reviewer's directory
#
# The target venue is read from state/project.md ("- Venue: ...") by this
# parent script and stated in each reviewer prompt — real reviewers know the
# venue; they still never see state/ itself.
#
# Note: CLI flags evolve. If an invocation fails, check `claude --help` /
# `codex --help` and adjust the two backend cases below. The temp-directory
# isolation does not depend on any flag.

set -euo pipefail

BACKEND="${BACKEND:-claude}"
ROUND="${1:?usage: review_panel.sh <round-number>}"
REPO="$(pwd)"
OUTDIR="${REPO}/state/reviews/round-${ROUND}"
AGENTS_DIR="${REPO}/.claude/agents"

[ -d "${REPO}/manuscript" ] || { echo "Run from the repository root." >&2; exit 1; }
command -v "${BACKEND}" >/dev/null 2>&1 \
    || { echo "Backend '${BACKEND}' is not installed or not on PATH." >&2; exit 1; }
mkdir -p "${OUTDIR}"

TASK=$'\n\nThe current working directory contains only the paper sources under\nmanuscript/ — that is everything you may read. Write your complete review\nnow, following the output format above exactly. Output only the review.'

# Venue name only: strip from the first parenthesis on, so author-side
# annotations on the template's "- Venue: X (page limit: ..., deadline: ...)"
# line never leak into reviewer prompts.
VENUE="$(grep -m1 -E '^- Venue:' state/project.md 2>/dev/null \
    | sed -e 's/^- Venue:[[:space:]]*//' -e 's/[[:space:]]*(.*$//' \
    | sed -e 's/[[:space:]]*$//' || true)"
[ -n "${VENUE}" ] && TASK="${TASK}"$'\n'"Target venue: ${VENUE} — apply that venue's standards."

if [ "${BRIEFING:-0}" = 1 ] && [ -d state/related-work/briefs ]; then
    TASK="${TASK}"$'\n'"A briefing/ folder is provided: source-verified one-page summaries of the closest prior work, curated by the authors. You may consult it; note in your review that you were briefed."
fi

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TMP_ROOT}"' EXIT

# Provenance: record which backend build produced this round.
"${BACKEND}" --version > "${OUTDIR}/backend-version.txt" 2>&1 || true

for persona in "${AGENTS_DIR}"/reviewer-*.md; do
    name="$(basename "${persona}" .md)"
    out="${OUTDIR}/${name}.md"
    echo ">>> ${name} -> ${out}"

    # Fresh, minimal working directory: the paper and nothing else.
    workdir="${TMP_ROOT}/${name}"
    mkdir -p "${workdir}"
    cp -r "${REPO}/manuscript" "${workdir}/manuscript"
    if [ "${BRIEFING:-0}" = 1 ] && [ -d "${REPO}/state/related-work/briefs" ]; then
        cp -r "${REPO}/state/related-work/briefs" "${workdir}/briefing"
    fi

    # Strip the YAML frontmatter; the remainder is the persona prompt.
    body="$(awk 'c==2{print} /^---$/{c++}' "${persona}")"
    prompt="${body}${TASK}"

    case "${BACKEND}" in
        claude)
            # --disallowedTools is defense in depth (note: --allowedTools only
            # pre-approves tools, it does not restrict availability).
            ( cd "${workdir}" && claude -p "${prompt}" \
                --disallowedTools "Write,Edit,NotebookEdit,Bash,WebFetch,WebSearch" \
            ) > "${out}"
            ;;
        codex)
            # read-only sandbox as defense in depth; drop the flag if your
            # local codex version does not support it.
            ( cd "${workdir}" && codex exec --sandbox read-only "${prompt}" ) > "${out}"
            ;;
        *)
            echo "Unknown BACKEND='${BACKEND}' (use claude|codex)" >&2; exit 1
            ;;
    esac

    rm -rf "${workdir}"
done

echo
echo "Panel complete: $(find "${OUTDIR}" -mindepth 1 -maxdepth 1 | wc -l) review file(s) in state/reviews/round-${ROUND}/."
echo "Next: ask the agent to run the meta-review step of the paper-review-panel skill."
