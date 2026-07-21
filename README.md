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

## Plugins

- [Project Steward](#project-steward-use-case) — cross-agent project
  stewardship plugin for Claude Code, Codex, and other coding agents.
- [Paperforge](#paperforge-use-case) - academic paper writing, mock review, revision, and paper workspace scaffolding.

### Use Case

#### Project Steward Use Case

Use Project Steward when working with an LLM coding agent on a project
that needs durable project memory, progress tracking, and clean handoff
across sessions or tools.

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

Then copy the Codex hook config into each target project where you want
Project Steward lifecycle behavior:

```bash
cd /path/to/your-project
mkdir -p .codex
cp /path/to/project-steward/plugin-src/codex/hooks/hooks.json .codex/hooks.json
```

Open `/hooks` in Codex and review/trust the hook configuration before
relying on it.

Example interactions:

- Ask agent to initialize Project Steward in a repository so future
  agents can read the project charter, plan, risks, decisions, and
  handoff state.
- Ask agent to resume a project after switching between Claude Code and
  Codex, using repository state instead of native chat history.
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

Example interactions:

- Ask agent to create a new Paperforge paper workspace.
- Ask agent to adopt an existing LaTeX repository in place.
- Start the intake interview for a new paper.
- Run a mock review panel before submission.

## License

MIT. See [LICENSE](LICENSE).
