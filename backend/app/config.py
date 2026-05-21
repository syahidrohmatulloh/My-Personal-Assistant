"""Application settings loaded from environment variables.

We use pydantic-settings so every env var is validated at startup. If something
is missing, the app refuses to start instead of crashing on the first request.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Anthropic
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # Voyage AI (embeddings for memory)
    VOYAGE_API_KEY: str

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str  # bypasses RLS — only used server-side
    SUPABASE_JWT_SECRET: str  # for verifying JWTs from the frontend

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Google Calendar OAuth foundation. Optional so the backend can boot before
    # Google OAuth is configured.
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_CALENDAR_REDIRECT_URI: str | None = None
    APP_FRONTEND_URL: str | None = None

    # Conversation Style Profile safety/cost controls
    # Upload can be large, but only a representative bounded sample is sent to Claude.
    STYLE_ANALYSIS_UPLOAD_MAX_CHARS: int = 5_000_000
    STYLE_ANALYSIS_SAMPLE_CHARS: int = 80_000
    STYLE_ANALYSIS_MAX_CHARS: int = 100_000

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]


settings = Settings()  # type: ignore[call-arg]
