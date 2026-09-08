# Layout Patterns

Use these patterns as defaults. Keep existing names when the repo already
has a clear equivalent.

## Skill-Only Development Repo

```
skill-src/
  skills/<skill-name>/SKILL.md
  skills/<skill-name>/references/
tools/
  build_skill_payloads.py
  publish_agent_artifact_pr.py
dist/
  skills/<skill-name>/
agent-artifacts.json
```

Publish `dist/skills/<skill-name>/` to `agent-skills` at the target path
chosen by the user.

## Plugin Development Repo

```
plugin-src/
  skills/
  references/
  claude/
  codex/
  metadata.json
tools/
  build_plugin_payloads.py
  publish_agent_artifact_pr.py
dist/
  <plugin-name>/...
agent-artifacts.json
```

Publish the generated plugin extraction tree to `agent-plugins`. Do not
keep separate hand-maintained Claude and Codex copies of shared skill text.

## Cross-Agent Rules

- Shared skills and references live once.
- Platform-specific commands, prompts, hooks, and manifests live in
  platform-specific source folders.
- Grok Build consumes the generated Claude payload (`skills/`,
  `commands/`, `hooks/`, `.claude-plugin/`). Do not author a third
  `plugin-src/grok/` copy of shared files.
- Generated dist folders must be reproducible from source.
- Build tools must identify an existing generated folder from stable platform
  manifests before replacing it. They must reject Git metadata and unrelated
  nonempty directories.
- Publication previews use a temporary checkout and print the artifact diff.
  A supplied target checkout must remain clean and unchanged.
- Tests should prove important generated files exist and unrelated platform
  files do not leak into the wrong payload.
