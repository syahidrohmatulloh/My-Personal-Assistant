"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat, conversations, journal, life_model, memories

app = FastAPI(
    title="My Assistant API",
    description="Personal AI assistant backend, Phase 1 MVP",
    version="0.1.0",
)

# CORS: the frontend (different origin) needs to call us. In production, lock
# this down to your actual Vercel URL via the ALLOWED_ORIGINS env var.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(memories.router)
app.include_router(life_model.router)
app.include_router(journal.router)


@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe. Hit this to confirm the service is running."""
    return {"status": "ok", "model": settings.ANTHROPIC_MODEL}
