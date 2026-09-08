---
name: agent-artifact-maintainer
description: Use when developing, reorganizing, packaging, or publishing agent skills/plugins; when skill or plugin repos have duplicated payload folders, messy layouts, missing build/dist scripts, unclear Claude/Codex/Grok distribution paths, or need PR publishing into agent-skills or agent-plugins.
---

# Agent Artifact Maintainer

Maintain agent skill/plugin development projects as development repos, not
raw install folders. Preserve one single canonical source, generate install
payloads, keep docs/tests aligned, and publish reviewable PRs.

## Workflow

1. **Survey first**: read tree, manifests, README/install docs, tests, CI,
   existing scripts, and git status. Detect skill-only, plugin-only, or
   cross-platform Claude/Codex plugin work (Grok reuses the Claude payload).
2. **Clarify intent only where needed**: ask about target agents, target
   repository, checked-in vs generated payloads, and publish destination.
   Do not ask questions the repo already answers.
3. **Normalize layout**: prefer one canonical authoring tree plus generated
   dist outputs. Do not duplicate shared `SKILL.md`, references, templates,
   prompts, or metadata across install payload folders.
4. **Maintain scripts**: create or update project-local build/dist scripts
   and a project-local publish script when repeated manual copy/publish work
   would otherwise be needed.
5. **Update docs and tests together**: README, install docs, CI, validators,
   and Project Steward state must match the new source and dist contract.
6. **Verify and commit**: test first for behavior changes, run the repo's
   verification commands, and commit semantic changes automatically. Never
   push without explicit approval.

## Layout Rules

Use `references/layout-patterns.md` when reorganizing a repo or creating
scripts. The default target is:

- canonical source under one obvious directory (`skill-src/`, `plugin-src/`,
  or equivalent already used by the repo);
- generated dist output under `dist/`, ignored unless the repo deliberately
  publishes generated artifacts;
- scripts under `tools/`;
- docs that explain how to extract the Claude Code, Codex, or generic skill
  payload from the development project. Grok Build installs the Claude
  payload (`grok plugin marketplace add` on the Claude marketplace
  directory, then `grok plugin install … --trust`); do not fork a third
  skills tree.

If a repo already has a clean equivalent layout, keep its names. Fix the
problem, not the vocabulary.

## Build And Dist Scripts

Create or update a deterministic build script when extraction requires more
than a simple copy. The script must:

- read canonical source only;
- clean stale output safely;
- generate platform-specific payloads without cross-contamination;
- filter caches and generated junk;
- fail loudly on missing expected files;
- have tests that pin important output paths.

Validate the output before any cleanup or copy. Accept new and empty
directories, plus an existing generated payload whose platform manifests match
the artifact's stable identity. A version difference is valid when rebuilding
an earlier release. Reject repository ancestors, Git metadata in the requested
or resolved path, source-tree overlaps, caller-controlled output-path symlinks,
and unrecognized nonempty directories. Preserve a non-final system alias
directly below the filesystem root.

Examples: Claude Code may need commands, hooks, and bundled runtime fallback
files; Codex may need skills, references, marketplace metadata, optional
prompts, and manual hook companions. Keep these decisions explicit.

## Publish PR Script

When publishing to `agent-skills` or `agent-plugins`, create or maintain a
project-local publish script. Preferred defaults:

- script: `tools/publish_agent_artifact_pr.py`
- config: `agent-artifacts.json`
- manifest fields: `name`, `kind`, `build_command`, `source_path`,
  `target_repo`, `target_path`, `base_branch`

On first publish, if `target_repo` is missing, ask for the target repository
and save it only after confirmation. Require an existing target checkout to be
clean before changing branches or copying files. Reject Git metadata and any
symlink in the configured artifact destination. Also reject ignored local files
inside that destination before replacing it without treating ignored files
elsewhere in the checkout as dirty. Stage and commit only that destination,
and verify the staged scope before committing.

The script must support `--dry-run`. A dry-run builds the source artifact,
creates a temporary preview from a supplied checkout or clone, and prints the
proposed Git diff without changing the target checkout's files, index, branch,
or commits. `--save-target-repo` reports its proposed manifest update during a
dry-run instead of writing it. Normal publication may open a PR with
`gh pr create`, but never merges it. If copying produces no changes, exit
without creating a PR.

## Guardrails

- Treat generated install payloads as disposable unless the user explicitly
  says the repo publishes generated files.
- Keep Claude Code and Codex experiences close, but respect platform
  differences instead of forcing identical folders. Grok reuses the
  Claude plugin directory rather than a third payload.
- Do not install packages, authenticate `gh`, push branches, or open network
  PR operations without the user's approval.
- Use Conventional Commits at semantic boundaries; include project-state
  files in the same commit when this is a Project Steward repo.
