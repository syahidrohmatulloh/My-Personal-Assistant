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
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Voice providers. Optional so the backend can boot before voice is configured.
    ELEVENLABS_API_KEY: str | None = None
    ELEVENLABS_VOICE_ID: str | None = None
    DEEPGRAM_API_KEY: str | None = None

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

    # Dual LLM provider architecture.
    # Chat remains Claude until utility pilots are stable.
    CHAT_LLM_PROVIDER: str = "claude"
    UTILITY_LLM_PROVIDER: str = "claude"
    UTILITY_LLM_MODEL: str = "claude-haiku-4-5"

    # Ollama / self-hosted local model settings for future utility pilots.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]


settings = Settings()  # type: ignore[call-arg]
