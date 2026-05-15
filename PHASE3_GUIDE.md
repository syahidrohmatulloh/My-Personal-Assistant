# Phase 3 — the life model

Phase 3 replaces the flat memory list with a structured *digital twin* — seven
tables that capture the user's identity, goals, relationships, emotional state,
life events, and the assistant's own observations about how to work with them.

The legacy `memories` table from Phase 2 stays in place as an unstructured
catch-all. The chat router now retrieves from both: structured first
(hierarchical), unstructured last (fallback).

This is the **most consequential schema decision** in the project. Future phases
build on it. Take care with rollout — but the rollout itself is just two SQL
files and the usual deploy.

---

## Design principles encoded in this phase

Four product principles, each enforced in actual code:

1. **Retrieval is hierarchical** — Identity > active goals > important people >
   recent mood > recent events > older memories. The `get_user_context()` SQL
   function returns data in this order; the prompt builder preserves it.

2. **Memory decay over time, never deletion** — `decay_inferred_confidence()`
   reduces confidence on AI-inferred rows by 0.05 every 30 days. Self-reported
   data is never decayed.

3. **User-authored truth dominates inferred truth** — when a self-report comes
   in, recently-inferred rows from the same hour are marked `superseded = true`.

4. **Subtle emotional intelligence** — the system prompt explicitly forbids
   performative or psychoanalytic responses. The assistant observes; it does
   not narrate the user's psyche back to them.

---

## Step 1 — run the schema migrations

Two SQL files. Run them in order in Supabase → SQL Editor:

1. `backend/schema_phase3.sql` — creates the seven tables, indexes, RLS
   policies, and the `get_user_context()` function.
2. `backend/schema_phase3_decay.sql` — adds the `decay_inferred_confidence()`
   function. (Scheduling it via pg_cron is optional and deferred.)

Verify: in Table Editor you should now see `user_identity`, `emotional_state`,
`people`, `relationship_notes`, `life_events`, `goals`, `goal_check_ins`, and
`self_reflections` alongside the existing tables.

## Step 2 — apply the code changes locally

Drop the contents of the Phase 3 zip into `~/my-assistant/`, preserving folder
structure. New backend files:

- `backend/app/services/life_model.py`
- `backend/app/services/prompt_builder.py`
- `backend/app/routers/life_model.py`
- `backend/schema_phase3.sql`
- `backend/schema_phase3_decay.sql`

Modified backend files:

- `backend/app/main.py` (registers the new router)
- `backend/app/routers/chat.py` (uses the prompt builder)

New frontend files:

- `frontend/app/identity/page.tsx`

Modified frontend files:

- `frontend/lib/api.ts` (Identity type + functions)
- `frontend/middleware.ts` (protects /identity)
- `frontend/components/chat/sidebar.tsx` (Identity link in sidebar footer)

No new Python dependencies. No new env vars.

## Step 3 — test locally

```
cd ~/my-assistant/backend
uv run uvicorn app.main:app --reload --port 8080
```

In another terminal:

```
cd ~/my-assistant/frontend
npm run dev
```

Open http://localhost:3000.

**Test the identity flow:**

1. Sidebar → **Identity**
2. Fill in name, location, role, values, and a short narrative
3. Save
4. Go to chat → New chat → ask: *"What do you know about me?"*
5. Claude should reference your identity (not just generic "I'm an AI" answer)

**Test that legacy memory still works:**

1. From the chat, mention something the previous extractor would catch
   (e.g., *"My favorite hobby is bouldering"*)
2. Wait 10 seconds, click **Memories** — should appear
3. The chat router uses both sources: life model + legacy memories

## Step 4 — deploy

Backend:

```
cd ~/my-assistant/backend
flyctl deploy
```

(No new secrets to set — Phase 3 uses no new external services.)

Frontend — push to GitHub, Vercel auto-deploys:

```
cd ~/my-assistant
git add -A
git commit -m "Phase 3: life model substrate"
git push
```

After both deploys finish, repeat the local tests on the production URL.

## What's NOT in Phase 3

Deliberately deferred. Each will live cleanly on top of this substrate without
schema migrations:

- **Daily journal** — Phase 4. The mood-capture UI and daily prompt that fills
  `emotional_state` and `life_events`.
- **The extraction pipeline writing to structured tables** — still uses the
  Phase 2 flat-memory path. Phase 4 graduates it.
- **Self-reflection engine** — the reflection table exists but nothing writes
  to it yet. The engine itself is Phase 6 or 7.
- **Tasks and projects** — Phase 5, designed alongside calendar integration.
- **Audit / correction UI** — exposing "downgrade this memory's confidence" in
  the UI. Phase 4 alongside journal.
- **Embeddings on life_events, people, etc.** — not needed until volumes grow.

## Troubleshooting

**Chat replies feel generic, like the assistant doesn't know me:** make sure
you've filled in Identity and saved it. Open `/identity` and confirm `Last
saved` shows a recent timestamp. Then check the backend logs (`flyctl logs`
or local terminal) — you should see `chat: user=... context_keys=['identity',
'recent_mood', 'active_goals', 'important_people', 'recent_events', ...]`. If
`identity` is missing from context_keys, the row didn't save.

**500 errors on /identity:** the `user_identity` table likely doesn't exist
yet. Re-run `schema_phase3.sql`. Safe to run multiple times.

**500 errors on /chat:** check that `get_user_context()` function was created.
In SQL Editor: `select get_user_context(auth.uid())` should return a JSON blob.

**Migration of existing Phase 2 memories:** they stay where they are. The chat
router reads both new (structured) and old (unstructured). Phase 4 will offer
to graduate suitable memories into structured tables.
