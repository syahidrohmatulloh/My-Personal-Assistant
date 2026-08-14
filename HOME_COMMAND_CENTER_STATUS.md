# HOME_COMMAND_CENTER_STATUS.md — Home OS

## Principle

One source of truth, two views.

- `/home` will become the calm command center / HUD.
- `/chat-v2` remains the conversation runtime.
- Home and Chat V2 must reuse the same assistant context loader.
- Supabase remains the memory source of truth.
- Old `/chat` remains fallback only.

## Current phase status

| Phase | Name | Status |
| --- | --- | --- |
| H0 | Shared Context Foundation | REVIEW |
| H1 | Home Shell | REVIEW |
| H2 | Real Cards | TODO |
| H3 | Handoff to Chat V2 | TODO |
| H4 | Context Health Strip | TODO |
| H5 | Cutover `/` to `/home` | TODO |

## H0 done when

- Shared context module exists at `frontend/lib/assistant-context/`.
- Old workspace paths are thin re-export shims.
- `/chat-v2` still looks and behaves the same.
- Build passes.
- Typecheck passes.

## H1 design note

Default ambient preset recommendation: `nebula-drift` for Life Companion.
Use `cosmic-fluid` later for Chief of Staff or interactive/voice moments.
\n\n## H2 — Real Vital Cards\n\nStatus: REVIEW\n\n`/home` now uses real assistant context data for agenda, reminders, brief, goals, memories, and people. `/` cutover remains untouched.\n\n\n## H3 — Conversation Handoff\n\nStatus: REVIEW\n\nHome composer and offer buttons now prefill `/chat-v2` via sessionStorage handoff. Auto-send is intentionally disabled. `/` cutover remains untouched.\n