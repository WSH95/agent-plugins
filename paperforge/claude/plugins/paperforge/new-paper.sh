#!/usr/bin/env bash
# Instantiate a new paper workspace from the template and initialize git.
#
# Usage: ./new-paper.sh [--steward] /path/to/my-paper
#
#   --steward   after scaffolding, seed .project-steward/ via the
#               project-steward CLI (when on PATH) using the AGENTS.md §12
#               answer key, then commit the seeded state. Without the CLI:
#               agent-route note when the Project Steward plugin (Claude
#               Code / Codex) is detected, loud no-channel warning when
#               nothing is — scaffolding always completes either way.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

STEWARD=0
while [ $# -gt 0 ]; do
    case "$1" in
        --steward) STEWARD=1; shift ;;
        --) shift; break ;;
        -*) echo "unknown option: $1 (usage: new-paper.sh [--steward] /path/to/my-paper)" >&2; exit 1 ;;
        *) break ;;
    esac
done
DEST="${1:?usage: new-paper.sh [--steward] /path/to/my-paper}"

[ -e "$DEST" ] && { echo "refusing to overwrite existing path: $DEST" >&2; exit 1; }

PARENT="$(dirname "$DEST")"
[ -d "$PARENT" ] || {
    echo "parent directory does not exist: $PARENT" >&2
    echo "create it first: mkdir -p \"$PARENT\"" >&2
    exit 1
}
DEST="$(cd "$PARENT" && pwd)/$(basename "$DEST")"

cp -r "${HERE}/template" "$DEST"
cd "$DEST"
chmod +x scripts/*.sh
git init -q
git add -A
git commit -qm "chore: initialize paper workspace from paperforge template" 2>/dev/null \
  || git -c user.name="paperforge" -c user.email="paperforge@local" commit -qm "chore: initialize paper workspace"

# Best-effort probe: is the Project Steward agent plugin installed for
# Claude Code (plugin registry / cache) or Codex (steward prompts)?
# Not finding it proves nothing — messages say "detected", never "installed".
steward_plugin_detected () {
    grep -qs '"project-steward@' "${HOME}/.claude/plugins/installed_plugins.json" \
      || compgen -G "${HOME}/.claude/plugins/cache/*/project-steward" >/dev/null \
      || [ -f "${HOME}/.codex/prompts/steward-init.md" ]
}

SEEDED=0
if [ "$STEWARD" = 1 ]; then
    if command -v project-steward >/dev/null 2>&1; then
        if project-steward init --root "$DEST" \
               --project-name "$(basename "$DEST")" \
               --one-liner "Academic paper workspace (pre-intake — see state/project.md)" \
               --primary-language "LaTeX + Markdown" \
               --build-command "make pdf" \
               --test-command "make check" \
               --backend markdown \
               --first-milestone "M1: intake + outline" \
               --yes >/dev/null; then
            if [ -n "$(git status --porcelain)" ]; then
                git add -A
                git commit -qm "chore: initialize Project Steward project management" 2>/dev/null \
                  || git -c user.name="paperforge" -c user.email="paperforge@local" commit -qm "chore: initialize Project Steward project management"
            fi
            SEEDED=1
            echo "Seeded .project-steward/ — first session: trim PROJECT.md/PLAN.md to point at state/ (AGENTS.md §12)"
        else
            echo "warning: project-steward init failed — the workspace is fine; run /project-steward:init in the first session (AGENTS.md §12)" >&2
        fi
    elif steward_plugin_detected; then
        echo "note: --steward: project-steward CLI not on PATH; agent plugin detected — run /project-steward:init in the first session (AGENTS.md §12)"
    else
        {
            echo "warning: --steward: no Project Steward channel detected — the CLI is"
            echo "  not on PATH and no agent plugin (Claude Code / Codex) was found."
            echo "  Install one:"
            echo "    CLI:    pipx install project-steward   (seeds at scaffold time)"
            echo "    plugin: https://github.com/WSH95/project-steward"
            echo "  then seed with 'adopt-paper.sh --steward' or /project-steward:init."
            echo "  The workspace itself is complete and works without steward."
        } >&2
    fi
fi

echo "Created ${DEST}"
echo
echo "Next steps:"
echo "  1. cd ${DEST}"
echo "  2. (optional) git remote add origin <private repo>   # cross-machine sync"
echo "  3. Start your agent (claude / codex) in this directory"
echo "  4. Say: \"Start the intake interview.\""
if [ "$SEEDED" = 0 ]; then
    echo "  5. (optional) Using Project Steward? Run /project-steward:init in the"
    echo "     first session — the answer key is in AGENTS.md §12"
fi
