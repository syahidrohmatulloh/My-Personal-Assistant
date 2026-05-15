# Retrieval & continuity audit — fixes

Applies the **P0 + P1** fixes from the audit. Conservative, no schema changes
to existing tables — only patches `get_user_context()`.

## What's fixed

**P0:**
1. **Memory dedup at extraction time.** Before inserting a new memory, we check
   if a near-identical one already exists (cosine similarity ≥ 0.92). If yes,
   skip. Stops the "User lives in Jakarta" pile-up.

2. **Timezone awareness.** Identity profile gains a `timezone` field
   (IANA name like `Asia/Jakarta`). Prompt builder uses it to render
   dates in the user's local timezone. New Identity field auto-detects
   the browser timezone as default.

3. **Identity rendered as prose** instead of JSON dump. Tokens spent on
   meaning, not braces. Tone instruction more natural to the model.

4. **Anti-repetition + no memory-dump directives** added to BASE_PROMPT.
   Stops the "I see you're a founder in Jakarta…" preamble on every reply.

**P1:**
5. **Name reinforcement** — name appears in BASE_PROMPT as an explicit
   "use their name naturally" instruction, last so it's freshest.

6. **Mood aggregation** — instead of dumping 7 itemized entries, we render
   an averaged trend plus up to 3 *self-reported* notes (notes have signal;
   the numeric ledger doesn't, per turn). Inferred observations summarized
   as a count.

7. **Language matching directive** in BASE_PROMPT.

8. **`get_user_context()` LIMIT bug fixed** — `limit 10` inside `jsonb_agg`
   doesn't actually limit. Patched to use a subquery so it does.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/retrieval-audit/. .
```

## SQL — run once in Supabase SQL Editor

```sql
-- Paste contents of:
--   backend/schema_phase3_context_fix.sql
```

It's a `create or replace function`, idempotent.

## Verify locally

```
cd ~/my-assistant/backend
pnpm exec true 2>/dev/null  # confirm pnpm doctrine even if backend uses uv
uv run uvicorn app.main:app --reload --port 8080

cd ~/my-assistant/frontend
pnpm dev
```

(Frontend = pnpm per doctrine. Backend Python via uv, unchanged.)

**Quick checks:**

1. Open `/identity`. Timezone field should show your browser tz (e.g. `Asia/Jakarta`). Save it.

2. New chat → ask something neutral like *"Apa kabar?"* (in Indonesian). Assistant should reply in Indonesian.

3. Have a chat that mentions a fact (e.g. *"I have two cats"*). Send another message about the same thing in another conversation a few minutes later. Then visit `/memories` — should see one entry, not two. Backend logs: `memory extraction: skipped dup`.

4. Send a turn with a topic unrelated to your stored facts. The assistant shouldn't recite your bio. If you ask *"What do you know about me?"*, it should still tell you.

5. If you've journaled multiple days: ask *"How has my mood been?"* — assistant should reference the trend ("you've averaged…") rather than spelling out each day's numbers.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Audit fixes: dedup, timezone, prose identity, anti-repetition"
git push
```

(Frontend deploy is whatever your pnpm-based pipeline runs on Vercel.)

## Files changed

- `backend/app/services/memory.py` — dedup logic added before insert
- `backend/app/services/prompt_builder.py` — full rewrite with prose, mood agg, anti-repetition, timezone, name reinforcement, language match
- `backend/schema_phase3_context_fix.sql` — `get_user_context()` LIMIT fix
- `frontend/app/identity/page.tsx` — timezone field

## What's NOT in this pass

Deferred to later phases per doctrine ("avoid premature overengineering"):

- **Smarter history trim with Haiku summarization.** Char-based trim is good enough until threads regularly cross 30+ turns.
- **Cross-conversation continuity via summary index.** Real fix is conversation-level summaries — Phase 5+ territory.
- **Self-reflection rendering as private hints** — implementation is here (the "do NOT recite these back" wrapping), but no engine writes reflections yet. So it's dormant code, ready when the engine arrives.
- **Tuning `MIN_SIMILARITY` threshold** — wait until you have real retrieval data to tune from.

## Honest caveats

- Dedup adds one Supabase RPC call per extracted memory. Extraction is in
  the background so user latency is unaffected. At scale this would batch;
  not worth optimizing yet.
- Mood trend math uses `statistics.mean` which is fine. We don't compute
  median or detect outliers — adds complexity that doesn't pay off until
  you have months of data.
- Timezone field is plain text. A picker dropdown is more user-friendly
  but adds a heavy `Intl` data dependency for marginal UX gain.
