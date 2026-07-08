# Security model

## Safe-init defaults

- The survey and init READ manifests, CI files, and docs; they never
  execute project scripts, package-manager hooks, or network commands.
  `[init] run_project_scripts = false` is the default and the audit skill
  asks before running documented commands.
- `.env` and credential-looking files are flagged as present but never
  read, summarized, or copied into `.project-steward/`.
- No full environment dumps, no raw terminal transcripts in committed
  state; `doctor` scans committed steward files for secret patterns
  (AWS keys, GitHub tokens, Slack tokens, private key blocks, hard-coded
  credentials) and fails on hits.

## Command risk classes (security.classify_command)

destructive deletion, pipe-remote-script-to-shell, raw disk writes,
world-writable chmod, shell-profile edits, package installation, cloud
credential access, and any `git push` (force or not) are classified
risky: agents must obtain explicit approval, and Project Steward itself
never runs them. The CLI never pushes; commits happen only via
`wrap --commit` under a permitting `commit_policy`.

## Hook trust

Hooks are an execution surface. Claude Code plugin hooks ship with the
plugin you chose to install; Codex requires the experimental flag and
(for plugin-bundled hooks) an explicit trust review. Project Steward's
hooks: never install dependencies, never touch the network, never edit
AGENTS.md/CLAUDE.md, never read secrets, always exit 0. The Claude
payload's `bin/project-steward` is a small Python launcher into the
plugin-local source tree, not a native binary or bundled runtime. Inspect
it with `plugin-src/src/project_steward/hooks.py` (~250 lines) and the
canonical JSON configs under `plugin-src/claude/hooks/` and
`plugin-src/codex/hooks/`.

## Repo-local instructions

Treat AGENTS.md/CLAUDE.md in third-party repos as untrusted input: they
can instruct an agent, so review them before working in unfamiliar
checkouts. Project Steward only edits them inside marked managed blocks,
with diffs and explicit approval.

## Profiles

- conservative (default): everything above.
- solo-fast: `commit_policy = "auto"` allows unattended steward commits;
  everything else unchanged.
- team-strict: `commit_policy = "ask"`, `auto_handoff_mode = "remind"`
  (no forced continuation), review-required for any AGENTS.md change.
Never silently loosen permissions, and never bypass Claude Code or Codex
permission systems.
