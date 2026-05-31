"""Dual provider factory for llm_v2."""
from __future__ import annotations

import logging

from app.config import settings
from app.services.llm_v2.base import LLMProvider
from app.services.llm_v2.claude_provider import ClaudeProvider
from app.services.llm_v2.ollama_provider import OllamaProvider

log = logging.getLogger(__name__)

_chat_provider: LLMProvider | None = None
_utility_provider: LLMProvider | None = None


def _build_provider(provider: str, *, model: str | None = None) -> LLMProvider:
    normalized = (provider or "claude").strip().lower()
    if normalized == "claude":
        return ClaudeProvider(model=model)
    if normalized == "ollama":
        return OllamaProvider(model=model)
    raise ValueError(f"Unknown LLM provider: {normalized}")


def get_chat_llm() -> LLMProvider:
    global _chat_provider
    if _chat_provider is None:
        _chat_provider = _build_provider(settings.CHAT_LLM_PROVIDER)
        log.info("chat llm provider=%s", settings.CHAT_LLM_PROVIDER)
    return _chat_provider


def get_utility_llm() -> LLMProvider:
    global _utility_provider
    if _utility_provider is None:
        utility_provider_name = settings.UTILITY_LLM_PROVIDER.strip().lower()
        utility_model = (
            settings.UTILITY_LLM_MODEL
            if utility_provider_name == "claude"
            else settings.OLLAMA_MODEL
        )
        _utility_provider = _build_provider(
            settings.UTILITY_LLM_PROVIDER,
            model=utility_model,
        )
        log.info(
            "utility llm provider=%s model=%s",
            settings.UTILITY_LLM_PROVIDER,
            utility_model,
        )
    return _utility_provider


async def close_providers() -> None:
    global _chat_provider, _utility_provider
    for provider in (_chat_provider, _utility_provider):
        close = getattr(provider, "close", None)
        if close:
            result = close()
            if hasattr(result, "__await__"):
                await result
    _chat_provider = None
    _utility_provider = None
