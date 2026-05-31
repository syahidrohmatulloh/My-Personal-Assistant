"""Claude provider for llm_v2.

Preserves Claude-native system blocks, cache_control, streaming, and multimodal blocks.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from app.config import settings
from app.services.llm_v2.base import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = AsyncAnthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)
        self.model = model or settings.ANTHROPIC_MODEL

    async def chat_with_system(
        self,
        system_blocks: list[dict],
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        if stream:
            return self._stream(system_blocks, messages, max_tokens, temperature)

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_blocks,
            messages=messages,
        )
        block = next((b for b in response.content if getattr(b, "type", None) == "text"), None)
        return getattr(block, "text", "") if block else ""

    async def _stream(
        self,
        system_blocks: list[dict],
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_blocks,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=[{"type": "text", "text": "You are a concise utility assistant."}],
            messages=[{"role": "user", "content": prompt}],
        )
        block = next((b for b in response.content if getattr(b, "type", None) == "text"), None)
        return getattr(block, "text", "").strip() if block else ""

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def supports_prompt_caching(self) -> bool:
        return True

    async def count_tokens(self, text: str) -> int:
        return max(1, len(text or "") // 4)
