# Phase 2 — deployment guide

This walks you through deploying the memory feature. Same pattern as Phase 1:
update database → update backend → update frontend → push to GitHub → CI deploys.

## Step 1 — Get a Voyage AI API key

1. Go to https://dash.voyageai.com (sign up if you don't have an account)
2. Free tier gives you 200 million tokens — far more than personal use needs
3. Left sidebar → **API Keys** → **Create new secret key**
4. Name it `my-personal-assistant`
5. **Copy the key now** (starts with `pa-`) — same as Anthropic, you only see it once

## Step 2 — Run the new schema in Supabase

1. Supabase dashboard → SQL Editor → New query
2. Paste the contents of `backend/schema_phase2.sql`
3. Run it. You should see "Success. No rows returned."
4. Verify: Table Editor → you should now see a `memories` table alongside `conversations` and `messages`

## Step 3 — Add Voyage key to local backend

```
cd ~/my-assistant/backend
open -e .env
```

Add this line below your existing `ANTHROPIC_API_KEY=` line:

```
VOYAGE_API_KEY=pa-your-key-here
```

Save and close.

## Step 4 — Install the new Python dependency locally

```
cd ~/my-assistant/backend
uv sync
```

This picks up `voyageai` and `pyjwt[crypto]` from the updated `pyproject.toml`.

## Step 5 — Test locally first

Start both services:

```
# Terminal 1
cd ~/my-assistant/backend
uv run uvicorn app.main:app --reload --port 8080

# Terminal 2
cd ~/my-assistant/frontend
npm run dev
```

Open http://localhost:3000. You should see:

- The same login → chat flow as before
- A new **Memories** link at the bottom of the sidebar
- After sending a chat message, when you visit the Memories page, you should see auto-extracted memories appearing (might take a few seconds — extraction runs after the response finishes)

Try this test sequence:

1. In a new chat, say: "Hi, my name is Syahid and I'm a software engineer based in Jakarta. I'm a fan of Manchester United."
2. Wait ~10 seconds (for background extraction)
3. Click Memories → you should see 2–3 memories about your name, job, location, and football team
4. Start a brand new chat, ask: "What football team do I support?"
5. Claude should answer correctly using the memory

If that works, you're ready to deploy.

## Step 6 — Deploy the backend

```
cd ~/my-assistant/backend
flyctl secrets set VOYAGE_API_KEY="pa-your-key-here"
flyctl deploy
```

Setting the secret triggers a rolling restart. Deploy pushes the new code.

Verify:

```
curl https://my-assistant-backend.fly.dev/health
```

Should return `{"status":"ok","model":"claude-sonnet-4-6"}` as before.

## Step 7 — Push frontend changes

The frontend changes (new memories page, sidebar link) need to land on GitHub.
Vercel will auto-deploy on push.

```
cd ~/my-assistant
git add -A
git commit -m "Phase 2: cross-conversation memory"
git push
```

Watch the Vercel dashboard — it should build and deploy in ~2 minutes.

## Step 8 — Test in production

1. Visit https://my-personal-assistant-lovat.vercel.app
2. Same drill — chat, wait, check memories page, start new chat, see if memory carries over
3. Use the chat that's running on Fly.io now, not your local one

## Troubleshooting

**Memories page is empty even after chatting:** background extraction may have failed. Check `flyctl logs` for `memory extraction:` lines. Most common cause is `VOYAGE_API_KEY` not set on Fly. Re-run the `flyctl secrets set` command from step 6.

**Chat is slow now:** the retrieval step adds one Voyage API call (~200ms) per turn. If it feels significantly slower, check `flyctl logs` for slow responses from Voyage. The `MIN_SIMILARITY` threshold in `memory.py` controls how aggressive retrieval is; raise it to 0.6 if memories feel noisy.

**Memory you don't want is showing up:** click Memories, delete it. The system will not re-extract identical content unless you give it identical context.

**"500 internal server error" on /memories endpoint:** likely the pgvector extension didn't enable or the `match_memories` function didn't get created. Re-run `backend/schema_phase2.sql` — it's safe to run multiple times.
