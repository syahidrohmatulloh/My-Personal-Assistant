from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.services import conversation_summary, memory
from app.services.memory_context_packer import pack_memory_context_for_prompt


@dataclass(frozen=True)
class ChatMemoryAssembly:
    legacy_memories: list[dict[str, Any]]
    related_summaries: list[dict[str, Any]]


async def retrieve_chat_memory_assembly(
    *,
    user_id: str,
    query_text: str,
    conversation_id: str,
    memory_limit: int = 12,
    summary_limit: int = 6,
) -> ChatMemoryAssembly:
    legacy_memories, related_summaries = await asyncio.gather(
        memory.retrieve_relevant(user_id, query_text, limit=memory_limit),
        conversation_summary.retrieve_related_summaries(
            user_id=user_id,
            query_text=query_text,
            exclude_conversation_id=conversation_id,
            limit=summary_limit,
        ),
    )

    return ChatMemoryAssembly(
        legacy_memories=list(legacy_memories or []),
        related_summaries=list(related_summaries or []),
    )


def pack_chat_memory_context(
    *,
    legacy_memories: list[dict[str, Any]],
    related_summaries: list[dict[str, Any]],
    query_text: str,
    user_id: str,
    logger: logging.Logger | None = None,
):
    packed_memory_context = pack_memory_context_for_prompt(
        legacy_memories=legacy_memories,
        related_summaries=related_summaries,
        query_text=query_text,
    )

    if logger is not None and (legacy_memories or related_summaries):
        logger.info(
            "chat: user=%s memory_context_packer: memories_in=%d memories_out=%d "
            "summaries_in=%d summaries_out=%d dropped_memories=%d dropped_summaries=%d "
            "packed_chars=%d intent=%s",
            user_id[:8],
            len(legacy_memories),
            packed_memory_context.memory_count,
            len(related_summaries),
            packed_memory_context.summary_count,
            packed_memory_context.dropped_memory_count,
            packed_memory_context.dropped_summary_count,
            packed_memory_context.total_chars,
            packed_memory_context.intent,
        )

    return packed_memory_context
