#!/usr/bin/env bash
# Add Paperforge scaffolding to an EXISTING LaTeX project without moving or
# overwriting the user's manuscript.
#
# Usage:
#   ./adopt-paper.sh /path/to/existing-paper
#   ./adopt-paper.sh --force /path/to/existing-paper   # overwrite, with .bak backups
#   ./adopt-paper.sh --steward /path/to/existing-paper # + seed .project-steward/
#                                                      #   (CLI on PATH; plugin-aware
#                                                      #   note/warning otherwise)
#   ./adopt-paper.sh --refresh <path> [--refresh <path>]... /path/to/existing-paper
#       Refresh-only mode: update ONLY the named template paths, keeping a
#       .bak-<timestamp> backup of anything overwritten; nothing else runs
#       (no scaffold pass, no git init). Meant for scaffolding files, e.g.
#       --refresh AGENTS.md. Careful with state/ paths: they hold YOUR
#       content and a refresh resets them (backups are kept).
#
# WARNING: --force replaces scaffolding files with pristine templates (each
# overwritten file is backed up as <file>.bak-<timestamp>). On a repo whose
# state/ is already filled in, this resets those files — normally you only
# want --force to refresh scripts/ or agent definitions.
#
# Behavior:
#   - Copies only the Paperforge scaffolding (AGENTS.md, CLAUDE.md, state/,
#     evidence/, scripts/, .claude/agents/, .codex/, Makefile, .gitignore).
#   - Never touches the existing manuscript. If the project has no manuscript/
#     directory, it detects \documentclass candidates and records them in
#     state/project.md so the agent asks the author which is the main file.
#   - Existing files are kept unless --force is given; --force backs up each
#     overwritten file as <file>.bak-<timestamp>.
#   - Idempotent: re-running only fills gaps.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="${HERE}/template"
FORCE=0
STEWARD=0
REFRESH=()

while [ $# -gt 0 ]; do
    case "$1" in
        --force)   FORCE=1; shift ;;
        --steward) STEWARD=1; shift ;;
        --refresh)
            [ $# -ge 2 ] || { echo "--refresh needs a template path" >&2; exit 1; }
            REFRESH+=("$2"); shift 2 ;;
        --) shift; break ;;
        -*) echo "unknown option: $1 (see the usage block at the top of this script)" >&2; exit 1 ;;
        *) break ;;
    esac
done
if [ "${#REFRESH[@]}" -gt 0 ] && [ "$FORCE" = 1 ]; then
    echo "--force with --refresh is redundant: refresh already overwrites with backups" >&2
    exit 1
fi
DEST="${1:?usage: adopt-paper.sh [--force|--steward] [--refresh <path>]... /path/to/existing-paper}"
[ -d "$DEST" ] || { echo "target path does not exist or is not a directory: $DEST" >&2; exit 1; }
DEST="$(cd "$DEST" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"

copy_item () {
    # copy_item <relative-path> ; copies file-by-file so we never clobber
    local rel="$1" src dst
    src="${TEMPLATE}/${rel}"
    if [ -d "$src" ]; then
        ( cd "$src" && find . -type f ) | while read -r f; do
            copy_item "${rel}/${f#./}"
        done
        return 0
    fi
    dst="${DEST}/${rel}"
    mkdir -p "$(dirname "$dst")"
    if [ -e "$dst" ]; then
        if cmp -s "$src" "$dst"; then
            return 0                      # identical: nothing to do
        elif [ "$FORCE" = 1 ]; then
            cp "$dst" "${dst}.bak-${STAMP}"
            cp "$src" "$dst"
            echo "  overwrote (backup kept): ${rel}"
        else
            echo "  kept existing:           ${rel}"
        fi
    else
        cp "$src" "$dst"
        echo "  added:                   ${rel}"
    fi
}

# Refresh-only mode: update just the named template paths, then stop.
if [ "${#REFRESH[@]}" -gt 0 ]; then
    FORCE=1
    echo "Refreshing scaffolding in ${DEST} ..."
    for rel in "${REFRESH[@]}"; do
        [ -e "${TEMPLATE}/${rel}" ] || { echo "not a template path: ${rel}" >&2; exit 1; }
        copy_item "$rel"
    done
    chmod +x "${DEST}"/scripts/*.sh 2>/dev/null || true
    echo "Refresh complete (overwritten files backed up as *.bak-${STAMP})."
    exit 0
fi

echo "Adopting ${DEST} ..."
for item in AGENTS.md CLAUDE.md .gitignore .gitattributes Makefile \
            state evidence scripts .claude .codex; do
    copy_item "$item"
done
chmod +x "${DEST}"/scripts/*.sh 2>/dev/null || true

# Manuscript layout: never force manuscript/. If absent, record candidates so
# the agent asks the author which .tex file is the main manuscript. The note
# is written once; re-runs must not append duplicates (idempotency).
if [ ! -d "${DEST}/manuscript" ] \
   && ! grep -qs "Adopted-repository note" "${DEST}/state/project.md"; then
    candidates="$( (cd "$DEST" && grep -rlsF --include='*.tex' '\documentclass' . 2>/dev/null | grep -v '\.bak-' | head -10) || true)"
    {
        echo ""
        echo "## Adopted-repository note (added by adopt-paper.sh, ${STAMP})"
        echo "This project was adopted in place; there is no manuscript/ directory."
        echo "Detected \\documentclass candidates for the main file:"
        if [ -n "$candidates" ]; then
            while IFS= read -r c; do echo "- $c"; done <<< "$candidates"
        else
            echo "- (none found — ask the author)"
        fi
        echo "Agent: ask the author which file is the main manuscript, record the"
        echo "answer in state/decisions.md, and treat its directory as the"
        echo "manuscript root everywhere the workflow says 'manuscript/'"
        echo "(including \`make check\` and the review panel)."
    } >> "${DEST}/state/project.md"
    echo "  note: no manuscript/ found; candidates recorded in state/project.md"
fi

# Git: initialize only if this is not already a repository.
if ! git -C "$DEST" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$DEST" init -q
    echo "  initialized new git repository"
fi

# Best-effort probe: is the Project Steward agent plugin installed for
# Claude Code (plugin registry / cache), Codex (steward prompts), or
# Grok Build (~/.grok/plugins)? Not finding it proves nothing —
# messages say "detected", never "installed".
grok_plugin_dir_named () {
    local name="$1" root d
    root="${HOME}/.grok/plugins"
    if [ -d "$root" ]; then
        [ -d "${root}/${name}" ] && return 0
        for d in "${root}"/*/"${name}" "${root}"/*/*/"${name}"; do
            [ -d "$d" ] && return 0
        done
    fi
    root="${HOME}/.grok/installed-plugins"
    [ -d "$root" ] || return 1
    for d in "${root}"/*; do
        [ -d "$d" ] || continue
        if [ -f "${d}/.claude-plugin/plugin.json" ] \
           && grep -qs "\"name\": \"${name}\"" "${d}/.claude-plugin/plugin.json"; then
            return 0
        fi
        [ "$(basename "$d")" = "$name" ] && return 0
    done
    return 1
}
steward_plugin_detected () {
    grep -qs '"project-steward@' "${HOME}/.claude/plugins/installed_plugins.json" \
      || compgen -G "${HOME}/.claude/plugins/cache/*/project-steward" >/dev/null \
      || [ -f "${HOME}/.codex/prompts/steward-init.md" ] \
      || grok_plugin_dir_named project-steward
}

# Optional Project Steward seeding. Adopt never commits — review git status.
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
            SEEDED=1
            echo "  seeded .project-steward/ — first session: trim PROJECT.md/PLAN.md per AGENTS.md §12"
        else
            echo "warning: project-steward init failed — the workspace is fine; run /project-steward:init in the first session (AGENTS.md §12)" >&2
        fi
    elif steward_plugin_detected; then
        echo "note: --steward: project-steward CLI not on PATH; agent plugin detected — run /project-steward:init in the first session (AGENTS.md §12)"
    else
        {
            echo "warning: --steward: no Project Steward channel detected — the CLI is"
            echo "  not on PATH and no agent plugin (Claude Code / Codex / Grok) was found."
            echo "  Install one:"
            echo "    CLI:    pipx install project-steward   (seeds at scaffold time)"
            echo "    plugin: https://github.com/WSH95/project-steward"
            echo "  then seed with 'adopt-paper.sh --steward' or /project-steward:init."
            echo "  The workspace itself is complete and works without steward."
        } >&2
    fi
fi

echo
echo "Adoption complete. Next steps:"
echo "  1. cd ${DEST}  (review 'git status' before committing the scaffolding)"
echo "  2. Start your agent (claude / codex / grok)"
echo "  3. Say: \"Start the intake interview.\""
if [ "$SEEDED" = 0 ]; then
    echo "  4. (optional) Using Project Steward? Run /project-steward:init in the"
    echo "     first session — the answer key is in AGENTS.md §12"
fi
