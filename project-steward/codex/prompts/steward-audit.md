Audit Project Steward docs against repository reality. If the
progress-tracking skill is installed, follow its doc-drift audit path;
otherwise use this condensed protocol.

1. Re-verify every command documented in AGENTS.md. Ask before running
   project build/test/lint commands.
2. Check referenced paths still exist, and check PLAN.md against the
   adopted task backend.
3. Run `project-steward doctor` if the CLI is installed.
4. Propose fixes as diffs. AGENTS.md and CLAUDE.md changes need explicit
   approval and a DECISIONS.md entry.

