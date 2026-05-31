"""Ollama provider for llm_v2.

Intended for utility tasks first. Main chat remains Claude until pilots are stable.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.services.llm_v2.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    async def chat_with_system(
        self,
        system_blocks: list[dict],
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        system_text = "\n\n".join(
            str(block.get("text") or "")
            for block in system_blocks
            if isinstance(block, dict) and block.get("text")
        )

        ollama_messages = []
        if system_text:
            ollama_messages.append({"role": "system", "content": system_text})

        for message in messages:
            role = str(message.get("role") or "user")
            content = message.get("content") or ""
            if isinstance(content, list):
                content = "\n".join(
                    str(part.get("text") or "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            elif not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            ollama_messages.append({"role": role, "content": content})

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": stream,
        }

        if stream:
            return self._stream(payload)

        response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        return str(data.get("message", {}).get("content") or "").strip()

    async def _stream(self, payload: dict) -> AsyncIterator[str]:
        async with self.client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = data.get("message", {}).get("content")
                if chunk:
                    yield str(chunk)

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": temperature, "num_predict": max_tokens},
            "stream": False,
        }
        response = await self.client.post(f"{self.base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        return str(data.get("message", {}).get("content") or "").strip()

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def supports_prompt_caching(self) -> bool:
        return False

    async def count_tokens(self, text: str) -> int:
        return max(1, len(text or "") // 4)

    async def close(self) -> None:
        await self.client.aclose()
