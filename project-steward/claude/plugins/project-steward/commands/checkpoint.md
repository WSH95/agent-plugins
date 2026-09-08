---
description: Record progress and refresh the handoff without ending the session.
---

Follow the **session-handoff** skill's auto-checkpoint mode: briefly
refresh HANDOFF.md (Now / In flight / Next steps / Blockers) and the
external-backend overview when changed, then run
`project-steward checkpoint --note "..."`, keep session_status active,
and report in one line. When nothing changed, leave files alone. Follow the
commit policy after coherent verified work; hooks never commit. $ARGUMENTS
