"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    attachments,
    briefing,
    chat,
    companion,
    companion_mood,
    conversations,
    journal,
    life_model,
    memories,
    memory_review,
    reflections,
    style_profiles,
    avatar_mode,
)
from app.services import memory_health_scheduler

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
app.include_router(companion.router)
app.include_router(companion_mood.router)
app.include_router(conversations.router)
app.include_router(memories.router)
app.include_router(memory_review.router)
app.include_router(life_model.router)
app.include_router(journal.router)
app.include_router(briefing.router)
app.include_router(attachments.router)
app.include_router(reflections.router)
app.include_router(style_profiles.router)
app.include_router(avatar_mode.router)




@app.on_event("startup")
async def start_memory_health_scheduler() -> None:
    await memory_health_scheduler.start_memory_health_scheduler()


@app.on_event("shutdown")
async def stop_memory_health_scheduler() -> None:
    await memory_health_scheduler.stop_memory_health_scheduler()

@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe. Hit this to confirm the service is running."""
    return {"status": "ok", "model": settings.ANTHROPIC_MODEL}
