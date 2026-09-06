"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    agent_core,
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
    calendar_oauth,
    voice,
)
from app.services import (
    memory_consolidation_scheduler,
    memory_health_scheduler,
    proactive_nudges,
    rate_limiter,
)
from app.services.token_crypto import token_encryption_configured

app = FastAPI(
    title="My Assistant API",
    description="Personal AI assistant backend, Phase 1 MVP",
    version="0.1.0",
)

# CORS: the frontend (different origin) needs to call us. In production, lock
# this down to your actual Vercel URL via the ALLOWED_ORIGINS env var.

@app.middleware("http")
async def lightweight_rate_limit_middleware(request, call_next):
    rate_limit_response = await rate_limiter.check_rate_limit(request)
    if rate_limit_response is not None:
        return rate_limit_response

    return await call_next(request)



app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(agent_core.router)
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
app.include_router(calendar_oauth.router)
app.include_router(voice.router)




@app.on_event("startup")
async def start_memory_health_scheduler() -> None:
    await memory_health_scheduler.start_memory_health_scheduler()
    await memory_consolidation_scheduler.start_memory_consolidation_scheduler()
    await proactive_nudges.start_proactive_nudge_scheduler()


@app.on_event("shutdown")
async def stop_memory_health_scheduler() -> None:
    await proactive_nudges.stop_proactive_nudge_scheduler()
    await memory_consolidation_scheduler.stop_memory_consolidation_scheduler()
    await memory_health_scheduler.stop_memory_health_scheduler()

@app.get("/health", tags=["meta"])
async def health():
    """Lightweight liveness/config probe.

    This intentionally avoids paid/slow external calls. It only reports whether
    required integrations appear configured, without exposing secret values.
    """
    return {
        "status": "ok",
        "model": settings.ANTHROPIC_MODEL,
        "supabase_configured": bool(
            settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY
        ),
        "google_calendar_configured": bool(
            settings.GOOGLE_CLIENT_ID
            and settings.GOOGLE_CLIENT_SECRET
            and settings.GOOGLE_CALENDAR_REDIRECT_URI
        ),
        "google_token_encryption_configured": token_encryption_configured(),
        "voice_tts_configured": bool(getattr(settings, "ELEVENLABS_API_KEY", None)),
        "voice_stt_configured": bool(getattr(settings, "DEEPGRAM_API_KEY", None)),
    }
