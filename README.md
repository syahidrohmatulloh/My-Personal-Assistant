# My Personal Assistant

An AI Chief of Staff / Life Companion built on Claude. Calm, intelligent presence with long-term memory, emotional continuity, and operational usefulness — without becoming a generic chatbot or AI girlfriend.

## Status

Currently on **Phase 4.15** — see [`CLAUDE.md`](./CLAUDE.md) for the full doctrine and roadmap.

Live deployments:
- Frontend: Vercel
- Backend: Fly.io (`my-assistant-backend`)
- Database: Supabase Postgres (with pgvector)

## What it does today

- **Conversational chat** with streaming responses
- **Cross-conversation memory** with structured identity, categorization, confidence scoring, and supersede-on-correction conflict resolution
- **Daily journal** with mood/energy/stress tracking and emotional baseline inference
- **Life model context** — identity, people, goals, relationship notes, life events
- **Companion mode** — opt-in framework from professional → friendly → affectionate → partner; only the partner tier unlocks dynamic mood and repair-gate behavior
- **User mood inference (Layer A)** — read-only, baseline-aware, informs tone without driving UI ambience or assistant affect
- **Style profiles** — teach the assistant to adapt communication style from real conversation transcripts
- **Daily briefings** — morning rollup of goals, mood, recent context
- **Attachments** — image and PDF support, vision-aware processing
- **Memory hygiene** — auto-cleanup of duplicates, deterministic age calculation from canonical ISO birthdays, supersede chain

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 (App Router) + React 19 + TypeScript + Tailwind |
| Backend | FastAPI + Python 3.12 via uv |
| AI | Claude Sonnet 4.6 (chat) + Haiku 4.5 (titles, classification, extraction) |
| Embeddings | Voyage AI `voyage-3.5-lite` (1024 dims) |
| Database | Supabase Postgres + pgvector |
| Auth | Supabase ES256 JWT via JWKS |
| Hosting | Frontend → Vercel · Backend → Fly.io (sin region) |

## Local development

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8080

# Frontend
cd frontend
pnpm install
pnpm dev
```

Required env vars in `backend/.env`:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ANTHROPIC_API_KEY`
- `VOYAGE_API_KEY`

Frontend env vars in `frontend/.env.local`:
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_URL`

## Schema

Incremental migrations live in `backend/schema_phase*.sql`. Replay them in numeric order to rebuild from scratch.

For a flat snapshot of the current production schema, see `backend/schema_snapshot.sql` (regenerate with `./scripts/dump_schema.sh`).

## Deploy

```bash
# Backend (Fly.io)
cd backend
flyctl deploy

# Frontend (Vercel) — auto-deploys on push to main
git push
```

## Philosophy

See [`CLAUDE.md`](./CLAUDE.md). Short version:

- Calm intelligent presence over enthusiastic helper
- Emotional realism without manipulation
- Continuity over flashiness
- Operational usefulness over dashboards
- Premium feel without therapy-app aesthetics
