# LLM Abstraction Layer v2 — Safe Migration Design

## Current status

Skeleton-only foundation. It does not change runtime behavior.

- `chat.py` is untouched.
- `conversation_summary.py` is untouched.
- Existing `app.services.claude.get_claude()` remains the active path.
- `CHAT_LLM_PROVIDER` defaults to `claude`.
- `UTILITY_LLM_PROVIDER` defaults to `claude`.

## Migration rules

1. Do not touch `backend/app/routers/chat.py` until at least three utility pilots are stable.
2. Start with low-risk utility calls only.
3. Preserve existing service signatures.
4. Rollback must be one-file or env-only whenever possible.
5. Claude remains primary for chat, vision, streaming, prompt caching, and personality nuance.

## Provider mapping

| Area | Default provider | Notes |
|---|---|---|
| Main chat | Claude | Keep existing path |
| Conversation summary | Utility provider | Future pilot |
| Title generation | Utility provider | Future pilot |
| Calendar extraction | Utility provider | Future pilot after summary/title |
| Vision/PDF | Claude | Keep existing path |

## Phase B pilot plan

Pilot `conversation_summary.py` by changing only the Haiku call site to use `get_utility_llm()`, while preserving existing Supabase, embedding, safe_execute, and retrieval logic.
