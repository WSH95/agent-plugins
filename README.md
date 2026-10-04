# agent-plugins

## Installing

Add this repository as a marketplace, then choose the plugin you want to
install from your agent's plugin picker.

Claude Code:

```text
/plugin marketplace add https://github.com/WSH95/agent-plugins
```

Codex:

```bash
codex plugin marketplace add https://github.com/WSH95/agent-plugins
```

Grok Build (reuses each plugin's Claude payload; no third folder):

```bash
grok plugin marketplace add https://github.com/WSH95/agent-plugins
grok plugin install project-steward --trust
grok plugin install paperforge --trust
```

`--trust` is required for lifecycle hooks. Skills and commands can also
appear from a Claude Code install via Grok's Claude compatibility, but
those hooks stay inert until Grok trusts the plugin.

cross-agent is the exception: Grok attaches it per project, as its
[use case](#cross-agent-use-case) says.

## Plugins

- [Project Steward](#project-steward-use-case) — cross-agent project
  stewardship plugin for Claude Code, Codex, Grok Build, and other
  coding agents.
- [Paperforge](#paperforge-use-case) - academic paper writing, mock review, revision, and paper workspace scaffolding.
- [cross-agent](#cross-agent-use-case) — run headless `claude`, `codex`, and
  `grok` processes as one team from Claude Code, Codex, or Grok.

### Use Case

#### Project Steward Use Case

Use Project Steward when working with an LLM coding agent on a project
that needs durable project memory, progress tracking, and clean handoff
across sessions or tools.

For Grok Build, install Project Steward from this marketplace (the
Claude plugin path) and pass `--trust` so hooks run. Use
`/session-resume` or `/project-steward:resume` for the repo-resident
recap — Grok's bare `/resume` is the native session picker.

For Codex, install Project Steward from this marketplace to get the
skills. To use the lifecycle hooks, first clone the source repository and
install the CLI:

```bash
git clone https://github.com/WSH95/project-steward.git
cd project-steward
pipx install .
project-steward --version
```

Enable Codex hooks if your Codex config or admin policy has disabled
them:

```toml
[features]
hooks = true
```

`project-steward init` writes `.codex/config.toml` and `.codex/hooks.json`
for the project it initializes, so most projects need no manual step
(`--no-codex-hooks` opts out). To add the hooks to a project that was
initialized earlier, copy the packaged config from this repository:

```bash
cd /path/to/your-project
mkdir -p .codex
cp /path/to/agent-plugins/project-steward/codex/hooks/hooks.json .codex/hooks.json
```

Open `/hooks` in Codex and review/trust the hook configuration before
relying on it.

Example interactions:

- Ask agent to initialize Project Steward in a repository so future
  agents can read the project charter, plan, risks, decisions, and
  handoff state.
- Ask agent to resume a project after switching among Claude Code,
  Codex, and Grok, using repository state instead of native chat history.
- Ask agent to checkpoint progress before a risky change, after a
  decision, or before ending a session.
- Ask agent to wrap up a session with a zero-context handoff for the next
  agent.

#### Paperforge Use Case

Use Paperforge when writing or revising an academic paper with an LLM agent.
It provides portable skills for intake, outlining, grounded drafting, related
work, polishing, mock peer review, and revision. It also includes a paper
workspace template with LaTeX, durable project state, reviewer personas, and
scaffold scripts for creating or adopting paper repositories.

Grok Build installs the Claude payload from this marketplace
(`grok plugin install paperforge --trust`). Slash commands are `/new-paper`
and `/adopt-paper` (qualified `/paperforge:…` if the bare name collides).
There is no Grok-only skills tree.

Example interactions:

- Ask agent to create a new Paperforge paper workspace.
- Ask agent to adopt an existing LaTeX repository in place.
- Start the intake interview for a new paper.
- Run a mock review panel before submission.

#### Cross-Agent Use Case

Use cross-agent when you want your Claude Code, Codex, or Grok session to
hand work to the other engines: a one-off review or question to another
model, or a whole team — planner, plan reviewer, implementer, parallel code
reviewers on different engines, and a resolver — that works each task in its
own git worktree and merges only tested, reviewed work. It needs Linux, git,
Node.js 24 or later, and the engine CLIs your roles use, signed in. Source
and full documentation:
[WSH95/cross-agent-cli](https://github.com/WSH95/cross-agent-cli).

For Claude Code, install `cross-agent` at user scope or with
`--scope local`, not `--scope project`, which every Claude specialist would
load. The plugin puts its operator CLI, `cross-agent`, on the session's Bash
tool path: ask Claude to run `cross-agent init --mode dev-team` in a project
to set up a team. A git repository with no config runs the one-consultant
`solo` mode with no setup.

For Codex, install it with `codex plugin add cross-agent@agent-plugins`.
Then ask Codex: **“Use cross-agent to set up its MCP connection once for this host.”**
Restart MCP or open a new session afterwards. The skill configures MCP for the CLI
and local Linux desktop Codex; each chat discovers its own project without a
per-session `CROSS_AGENT_PROJECT` or a versioned cache path. A git repository with
no config runs `solo`. For a team, ask the skill to initialize the project with
`dev-team` or `dev-team-engine`.

Install and update through the marketplace as usual. The connection follows the
installed version on reconnect. The skill also checks or removes the setup:
[Install it in Codex](https://github.com/WSH95/cross-agent-cli/blob/main/docs/install.md#install-it-in-codex).

For Grok Build, attach cross-agent per project from a clone of the source
repository rather than with `grok plugin install`, which would load it in
every Grok session:
[Install it in Grok](https://github.com/WSH95/cross-agent-cli/blob/main/docs/install.md#install-it-in-grok).
Grok also loads the plugins Claude Code installs, so with both on one
machine, see that guide's Claude Code section for the switch.

Example interactions:

- Ask agent to have Codex review a file through cross-agent and report
  what it finds.
- Ask agent to use the cross-agent dev team to implement a change, with the
  plan reviewed first and the branch reviewed by Claude, Codex, and Grok in
  parallel.
- Ask agent what the team is doing, or answer a lead's question from a
  terminal with `cross-agent answer`.

## License

MIT. See [LICENSE](LICENSE). cross-agent carries its own MIT
license in its payload, `cross-agent/*/plugins/cross-agent/LICENSE`.
