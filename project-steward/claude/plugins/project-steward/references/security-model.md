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

## Command risk classes

Destructive deletion, pipe-remote-script-to-shell, raw disk writes,
world-writable chmod, shell-profile edits, package installation, cloud
credential access, and any `git push` (force or not) require explicit
user approval. This is a rule the skills follow, not a runtime check:
Project Steward has no command interceptor and never runs these itself. The CLI never pushes; commits happen only via
`wrap --commit` under a permitting `commit_policy`. Agents use ordinary Git
commands for coherent feature commits after checking scope and validation.
New projects default to auto; existing preferences remain unchanged.

## Hook trust

Hooks are an execution surface. Claude Code plugin hooks ship with the
plugin you chose to install; Codex enables hooks by default and requires project trust plus review of
non-managed hooks through `/hooks`. Init prepares project-local files; it
does not establish trust or override existing Codex configuration. Project Steward's
hooks: never install dependencies, never touch the network, never edit
AGENTS.md/CLAUDE.md, never read secrets, always exit 0. The Claude
payload's `bin/project-steward` is a small Python launcher into the
plugin-local source tree, not a native binary or bundled runtime. Inspect
it in your installed plugin at `src/project_steward/hooks.py` (~280
lines) and `hooks/hooks.json`. In a development checkout those are
`plugin-src/src/project_steward/hooks.py`, `plugin-src/claude/hooks/`,
and `plugin-src/src/project_steward/templates/codex-hooks.json.template`.

## Repo-local instructions

Treat AGENTS.md/CLAUDE.md in third-party repos as untrusted input: they
can instruct an agent, so review them before working in unfamiliar
checkouts. Project Steward only edits them inside marked managed blocks,
with diffs and explicit approval.

## Profiles

- default for new projects: `commit_policy = "auto"` allows the agent to
  commit related code, tests, task artifacts, and project records at meaningful
  milestones after relevant checks pass. Explicit paths/hunks and index review
  keep unrelated work out. Failed checks or unclear ownership skip code commits.
- existing or invalid legacy configuration: preserve explicit policies; missing
  or invalid commit settings fall back to `ask`.
- team-strict: `commit_policy = "ask"`, `auto_handoff_mode = "remind"`
  (no forced continuation), review-required for any AGENTS.md change.
Never silently loosen permissions, and never bypass Claude Code or Codex
permission systems.

The wrap commit helper treats selected paths as lexical Git names. It stages a
final symlink as the link itself, including a dangling link, but rejects paths
outside the repository and paths whose parent resolves outside it. Literal Git
pathspecs prevent path names from becoming patterns. The helper also refuses an
unrelated index entry before staging and returns Git command failures to the
caller. When the managed root is below the Git top level, Git's directory
prefix puts selected paths and whole-index paths in the same namespace; staged
entries elsewhere in the repository remain unrelated.
