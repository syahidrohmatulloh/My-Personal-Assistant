# My Assistant — Phase 1 MVP

A personal AI assistant. Next.js frontend, FastAPI backend, Supabase database,
Claude API.

This is **Phase 1** — chat with memory inside a single conversation, multiple
saved conversations, streaming responses, auth. No tool use, no cross-chat
memory, no workflows yet — those come in later phases.

---

## What you'll set up

```
my-assistant/
├── frontend/   # Next.js app (Vercel)
└── backend/    # FastAPI app (Fly.io)
```

Both talk to a single Supabase project for auth and data.

## Prerequisites

You'll need accounts on:

1. **Supabase** — https://supabase.com (free tier)
2. **Anthropic** — https://console.anthropic.com ($5 free credit on signup)
3. **Vercel** — https://vercel.com (free hobby tier)
4. **Fly.io** — https://fly.io (free allowance, requires credit card for verification)

And these installed locally:

- **Node.js 20+** — for the frontend
- **Python 3.11+** — for the backend
- **uv** — fast Python package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **flyctl** — Fly.io CLI: `curl -L https://fly.io/install.sh | sh`

---

## Step 1 — Supabase project

1. Create a new project at supabase.com. Pick the region closest to you.
2. Wait for it to provision (~2 minutes).
3. **Run the schema.** In the dashboard: SQL Editor → New Query → paste the
   contents of `backend/schema.sql` → Run. This creates the `conversations`
   and `messages` tables, indexes, and Row-Level Security policies.
4. **Grab your keys.** Settings → API. Copy these — you'll need them in a moment:
   - Project URL (`SUPABASE_URL`)
   - `anon public` key (`NEXT_PUBLIC_SUPABASE_ANON_KEY`)
   - `service_role` key (`SUPABASE_SERVICE_ROLE_KEY`) — **never expose to the browser**
   - JWT Secret (`SUPABASE_JWT_SECRET`) — under "JWT Settings"
5. (Optional but recommended) **Disable email confirmations** for personal use.
   Authentication → Providers → Email → toggle off "Confirm email". Lets you
   sign in immediately after signup.

## Step 2 — Anthropic API key

1. Log into console.anthropic.com.
2. API keys → Create key. Copy it (`sk-ant-...`) — you only see it once.

---

## Step 3 — Backend (local dev)

```bash
cd backend
cp .env.example .env
# Edit .env and fill in: ANTHROPIC_API_KEY, SUPABASE_URL,
# SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET.

uv sync                          # installs dependencies
uv run uvicorn app.main:app --reload --port 8080
```

You should see `Uvicorn running on http://0.0.0.0:8080`.
Test it: open http://localhost:8080/health — you should get `{"status": "ok", ...}`.

API docs are auto-generated at http://localhost:8080/docs.

## Step 4 — Frontend (local dev)

In a new terminal:

```bash
cd frontend
cp .env.example .env.local
# Edit .env.local: fill NEXT_PUBLIC_SUPABASE_URL and
# NEXT_PUBLIC_SUPABASE_ANON_KEY. NEXT_PUBLIC_API_URL is already set to
# http://localhost:8080 for local dev.

npm install
npm run dev
```

Open http://localhost:3000. You'll be redirected to `/login`. Click "Sign up",
create an account, and you should land in the chat. Send a message — you
should see Claude's reply stream in token by token.

If anything fails:
- Browser console + Network tab will show frontend errors
- The terminal running `uvicorn` will show backend errors
- Most "it doesn't work" issues at this stage are env vars — double-check `.env` files

---

## Step 5 — Deploy the backend (Fly.io)

```bash
cd backend
fly auth signup   # or `fly auth login` if you have an account
fly launch --no-deploy
# Answer the prompts. Use the existing fly.toml when asked. Pick a region
# close to you (sin = Singapore, iad = US East, ams = Amsterdam, etc.)

# Push your secrets — never commit these to git!
fly secrets set \
  ANTHROPIC_API_KEY=sk-ant-... \
  SUPABASE_URL=https://YOUR_PROJECT.supabase.co \
  SUPABASE_SERVICE_ROLE_KEY=eyJ... \
  SUPABASE_JWT_SECRET=your-jwt-secret \
  ALLOWED_ORIGINS=https://YOUR_APP.vercel.app

fly deploy
```

After deploy, you'll get a URL like `https://my-assistant-backend.fly.dev`.
Test it: `curl https://my-assistant-backend.fly.dev/health`.

## Step 6 — Deploy the frontend (Vercel)

The easiest path: push this repo to GitHub, then in Vercel:

1. Add New → Project → Import from GitHub.
2. **Root Directory: `frontend`** (important — this is a monorepo).
3. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_URL` → your Fly.io URL from step 5
4. Deploy.

Once deployed, go back to Fly.io and update `ALLOWED_ORIGINS` to include your
real Vercel URL:

```bash
fly secrets set ALLOWED_ORIGINS=https://your-app.vercel.app
```

(Cookie issues? Make sure Supabase Auth → URL Configuration includes your
Vercel domain.)

---

## What this app does and doesn't do

✅ Email/password auth
✅ Multiple conversations per user
✅ Streaming responses
✅ Markdown + code highlighting
✅ Mobile responsive
✅ Conversation history persists
✅ RLS enforces per-user data isolation

❌ No cross-conversation memory (Phase 2)
❌ No web search, no tool use (Phase 3)
❌ No scheduled workflows (Phase 4)
❌ No production observability (Phase 5)

## Costs at personal scale

- Supabase: $0 (free tier — 500 MB DB, 50k MAU)
- Anthropic: pay per use, ~$0.005 per typical chat turn with Sonnet 4.6
- Fly.io: $0 if you let machines auto-stop (~5s cold start)
- Vercel: $0 hobby tier

Expect **$5–15/month** in API costs at solo daily-use volume.

## Next steps

Use it for two weeks. Notice what's missing. Then move on to Phase 2 (cross-conversation memory) with the
roadmap document.

## Troubleshooting

**"Not authenticated" on every backend call.** The frontend can't see your
JWT. Check `NEXT_PUBLIC_API_URL` is set, and the Supabase URL Configuration
in your project allows your domain.

**CORS error in browser console.** `ALLOWED_ORIGINS` in the backend doesn't
include your frontend's origin. Update with `fly secrets set ALLOWED_ORIGINS=...`
and redeploy. For local dev, it's `http://localhost:3000`.

**"Invalid token" 401.** `SUPABASE_JWT_SECRET` is wrong. Supabase dashboard
→ Settings → API → JWT Secret → copy that exact value.

**Streaming feels chunky.** Some proxies buffer SSE. The `X-Accel-Buffering: no`
header tells nginx-style proxies not to. If using Cloudflare in front, also
turn on "Bypass cache for streaming endpoints" or it'll buffer.

**Cold starts on Fly.io.** Set `min_machines_running = 1` in `fly.toml` and
redeploy. Costs ~$2/month for always-on.
