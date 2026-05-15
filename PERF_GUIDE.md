# Perf pass — apply

## 1. Apply both zips

```
cd ~/my-assistant
cp -R ~/Downloads/perf-backend/. .
cp -R ~/Downloads/perf-frontend/. .
```

## 2. Install new frontend dep

```
cd ~/my-assistant/frontend
npm install
```

(Picks up `@tanstack/react-query`.)

## 3. Backend env var on Fly — add FLY_BACKEND_URL on Vercel side

The edge proxy needs to know where to forward. On **Vercel** dashboard → Project Settings → Environment Variables, add:

```
FLY_BACKEND_URL = https://my-assistant-backend.fly.dev
```

(No new secrets on Fly itself.)

## 4. Test locally

```
# backend
cd ~/my-assistant/backend
uv run uvicorn app.main:app --reload --port 8080

# frontend (in another terminal)
cd ~/my-assistant/frontend
npm run dev
```

Set `FLY_BACKEND_URL=http://localhost:8080` in `frontend/.env.local` for the proxy to work locally.

Verify:
- Sidebar shows skeletons briefly then conversations
- Clicking New chat — conversation appears instantly (optimistic), then updates with real ID
- Sending first message — title updates within 5s (Haiku background job)
- Streaming feels smoother (rAF batching reduces re-renders)
- Backend logs show parallel pipeline: `context_keys=[...]` line includes `history_len`

## 5. Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Perf: parallel pipeline, prompt cache, React Query, edge proxy, rAF batching"
git push
```

Vercel auto-deploy. Confirm `FLY_BACKEND_URL` is set in Vercel env vars before deploy lands.

## 6. SQL — run in Supabase

```sql
-- Faster history fetch (recent N messages)
create index if not exists messages_conversation_id_created_at_desc_idx
    on messages (conversation_id, created_at desc);

-- get_user_context hot path
create index if not exists emotional_state_user_super_observed_idx
    on emotional_state (user_id, superseded, observed_at desc)
    where superseded = false;

-- Tighter ivfflat for small memory volumes
drop index if exists memories_embedding_idx;
create index memories_embedding_idx
    on memories using ivfflat (embedding vector_cosine_ops)
    with (lists = 10);
```

## Expected wins

- First-token latency: -600ms to -900ms (parallel pipeline)
- Recurring cost: -90% on cached system prompt portion
- Cold start: eliminated (`min_machines_running=1`, ~$2/mo)
- Streaming jank: gone (rAF batching, memo)
- Sidebar pop: gone (server-rendered + skeletons)
- Optimistic UX: New chat / delete feel instant

## Honest caveats

- The edge proxy adds one hop (browser → Vercel edge → Fly). In most regions this is faster overall because Vercel edge is closer to the user than Fly Singapore. For users in Singapore itself, it's roughly neutral.
- Prompt caching needs the system prompt > ~1024 tokens to activate. Your BASE_PROMPT plus rendered context usually clears this — but if you have an empty identity and no memories, cache won't engage.
- History trim is char-based, not token-based. Good enough for v1; replace with Haiku-summarization in a future phase if you hit long-thread issues.
