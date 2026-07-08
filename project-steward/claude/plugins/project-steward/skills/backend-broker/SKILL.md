---
name: backend-broker
description: Choose, explain, adopt, or migrate a task/spec backend (built-in Markdown, Backlog.md, beads, CCPM, Taskmaster, GitHub Spec Kit, GitHub Issues) for a Project Steward project. Use when the user asks which task tracker or issue system to use, mentions any of those tools, complains that PLAN.md is getting unwieldy or tasks are a mess, plans multi-agent or PRD-driven work, or during project-init's backend question. The user should NOT need to know these tools in advance - explain in plain English, get approval, never install anything silently.
---

# Backend broker

One system owns fine-grained tasks at a time. The broker's job is to pick
it deliberately, explain it plainly, and switch it safely.

## Flow

1. **Detect + score**: `project-steward backend recommend --json`
   (detection probes repo artifacts and PATH binaries; scoring uses open
   task count, blocker count, GitHub remote, PRD presence, and what is
   already in use — see ../../references/backend-selection.md). Without the
   CLI, inspect for `.beads/`, `backlog/`, `.claude/epics|prds/`,
   `.taskmaster/`, `.specify/`, and `gh`.
2. **Explain in plain English first** — one sentence per candidate about
   what daily use feels like, assuming zero prior knowledge. Offer the
   expert view (signals, scores, trade-offs, migration consequences) only
   if asked or if the user is clearly expert.
3. **Get approval**, then `project-steward backend adopt <name>` — it
   shows the AGENTS.md `task-backend` block diff, requires confirmation,
   and records `backend.json`. Then trim `PLAN.md` to milestones + a
   pointer (never two task lists) and move existing open tasks into the
   backend with the user.
4. **Install assistance**: print the install command/repo link for the
   user's OS and ask before running anything. Never `curl | sh`, never
   package-install, never `gh auth`, without explicit approval. Verify
   the tool answers (`bd --version`, `backlog --version`, ...) after an
   approved install.

## Rules of thumb

| Situation | Recommend |
| --- | --- |
| Tiny/solo, few tasks, zero-dependency preference | built-in Markdown |
| Wants Kanban/structure but staying in Markdown | Backlog.md |
| Dependency-heavy, many blockers, multi-agent, task claiming | beads |
| GitHub Issues as source of truth, PRD → epic → issues | CCPM |
| PRD-to-task decomposition focus | Taskmaster |
| Formal spec/plan gate before code | Spec Kit |
| Team already lives in GitHub Issues | GitHub Issues (gh) |
| Linear / Jira | explicit stubs — not implemented; say so honestly |

## Migration triggers (proactive, once per threshold)

Suggest revisiting the backend when: > 25 open PLAN.md tasks; ≥ 5
blockers/dependencies; multiple active agents; repeated PLAN.md merge
conflicts; issue IDs appearing in commits/PRs that the current backend
doesn't track. Migration = adopt new backend → move open tasks with the
user → old system's tasks closed or archived → `DECISIONS.md` entry.

## Never

Silently install, silently switch, duplicate task lists across systems,
or make a backend canonical without the user's explicit approval.
