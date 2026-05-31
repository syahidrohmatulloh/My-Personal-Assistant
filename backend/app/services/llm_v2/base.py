"""LLM Provider Interface for Aliyya.

Skeleton-only. No runtime service imports this yet.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    @abstractmethod
    async def chat_with_system(
        self,
        system_blocks: list[dict],
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        raise NotImplementedError

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def supports_vision(self) -> bool:
        raise NotImplementedError

    @property
    @abstractmethod
    def supports_prompt_caching(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        raise NotImplementedError
