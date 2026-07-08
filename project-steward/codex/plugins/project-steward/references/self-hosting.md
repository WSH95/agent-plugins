# Self-hosting (dogfooding)

The Project Steward repository manages itself: root AGENTS.md (with the
managed protocol block), CLAUDE.md adapter, and a real
`.project-steward/` describing this repo's own plan, handoff, risks, and
verification. Purpose: any future agent maintains the tool using the
tool.

Maintenance protocol for future agents:

1. Read `.project-steward/HANDOFF.md`; run `project-steward resume`.
2. Run `project-steward doctor --self` before and after changes.
3. Preserve migration compatibility (`.projectforge/` detection, the
   `projectforge` alias) until a documented deprecation window ends.
4. Keep Ubuntu/Windows/macOS support; no Bash-only core behavior.
5. Update tests when changing templates, hooks, CLI surface, or state
   schema; keep `python -m pytest` green.
6. Checkpoint PROGRESS.md/HANDOFF.md at boundaries; propose Conventional
   Commits; never push without approval.

Durable-but-not-noisy rule: the repo commits its own steward state files,
while `.project-steward/runtime/` stays ignored like any managed project.
