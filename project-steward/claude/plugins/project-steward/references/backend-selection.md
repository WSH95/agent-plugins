# Backend selection

One system owns fine-grained tasks at a time; PLAN.md degrades to
milestones + a pointer when an external backend is adopted.

## Detection

Repo artifacts and PATH binaries: beads (`.beads/`, `bd`), Backlog.md
(`backlog/`, `backlog`), CCPM (`.claude/prds|epics/`), Taskmaster
(`.taskmaster/`, `task-master`), Spec Kit (`.specify/`, `specs/`,
`specify`), GitHub Issues (`gh` + github.com remote). Artifacts already
in the repo score +50 (in use beats theoretically better).

## Scoring signals

open PLAN.md checkbox count, HANDOFF blocker count, GitHub remote,
PRD/spec presence, tools on PATH. Rules: Markdown for small/solo;
Backlog.md for 10-25 open tasks wanting structure-in-Markdown; beads for
>= 3 blockers or > 25 tasks or multi-agent claiming; CCPM for GitHub
Issues + PRD traceability; Taskmaster for PRD decomposition; Spec Kit for
spec-gated work; GitHub Issues when the team already lives there. Linear
and Jira are honest stubs (recommendable never, mentionable always).

## Migration triggers (proactive)

> 25 open Markdown tasks; >= 5 blockers/dependencies; multiple active
agents; repeated PLAN.md merge conflicts; issue IDs in commits/PRs the
backend doesn't track.

## Adoption procedure

recommend -> plain-English explanation -> approval -> `backend adopt`
(AGENTS.md task-backend block diff + backend.json) -> move open tasks
with the user -> DECISIONS.md entry. Installation is assisted, never
silent, and install commands are labeled "verify against upstream README"
because installers drift.

Upstream links: https://github.com/MrLesk/Backlog.md ·
https://github.com/steveyegge/beads · https://github.com/automazeio/ccpm ·
https://github.com/eyaltoledano/claude-task-master ·
https://github.com/github/spec-kit · https://cli.github.com
