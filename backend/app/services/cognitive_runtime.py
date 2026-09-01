"""M31D — CognitiveRuntime facade foundation.

The runtime is a facade around existing cognitive services.

M31D established the facade. M31E incrementally moves orchestration
responsibilities through that facade without changing underlying algorithms.

Current ownership:
- delegate WorkingMemoryState lifecycle to the existing M31C builder;
- delegate cognitive trace finalization/emission to the existing M31B service;
- own trace-sink configuration for one runtime instance;
- delegate life-model context retrieval to the existing life-model service;
- delegate memory retrieval/summary fan-in to the existing chat-memory assembly service;
- delegate memory-context packing to the existing chat-memory assembly service.

Calendar routing, prompt assembly, LLM generation, and persistence remain
outside CognitiveRuntime at this extraction step.

Dependency direction:
    chat.py -> CognitiveRuntime -> existing services

Existing services must never depend on CognitiveRuntime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services import chat_memory_assembly
from app.services import cognitive_trace
from app.services import life_model
from app.services import working_memory


COGNITIVE_RUNTIME_VERSION = "M31D-v1"


@dataclass(frozen=True)
class CognitiveRuntime:
    """Facade for incrementally migrated cognitive orchestration."""

    trace_sink: cognitive_trace.TraceSink
    logger: logging.Logger | None = None
    version: str = COGNITIVE_RUNTIME_VERSION

    def build_working_memory(
        self,
        **kwargs: Any,
    ) -> working_memory.WorkingMemoryState:
        """Own the M31C WorkingMemoryState lifecycle boundary.

        M31D-1 delegates to the authoritative M31C builder without changing
        its semantics. The facade performs no retrieval, policy decision,
        prompt construction, model call, or persistence.
        """

        return working_memory.build_working_memory_state(
            **kwargs
        )

    async def retrieve_life_context(
        self,
        *,
        user_id: str,
        mood_days: int = 14,
    ) -> dict[str, Any]:
        """Own the M31E life-context retrieval boundary.

        The authoritative durable-data query remains life_model.get_context().
        This facade preserves the existing chat-level fail-open behavior:
        unavailable or invalid context degrades to an empty dictionary.
        """

        try:
            context = await life_model.get_context(
                user_id,
                mood_days=mood_days,
            )
        except Exception as exc:  # noqa: BLE001
            if self.logger is not None:
                self.logger.warning(
                    "life_model.get_context failed user=%s: %s",
                    user_id[:8],
                    exc,
                )
            return {}

        return (
            context
            if isinstance(
                context,
                dict,
            )
            else {}
        )

    async def retrieve_chat_memory_assembly(
        self,
        *,
        user_id: str,
        query_text: str,
        conversation_id: str,
        memory_limit: int = 12,
        summary_limit: int = 6,
    ) -> chat_memory_assembly.ChatMemoryAssembly:
        """Own the M31E retrieval-orchestration boundary.

        The authoritative retrieval gate, embedding, RPC, ranking, summary
        retrieval, fan-in, and diagnostics behavior remains in the existing
        memory and chat_memory_assembly services.
        """

        return await chat_memory_assembly.retrieve_chat_memory_assembly(
            user_id=user_id,
            query_text=query_text,
            conversation_id=conversation_id,
            memory_limit=memory_limit,
            summary_limit=summary_limit,
        )

    def pack_chat_memory_context(
        self,
        *,
        legacy_memories: list[dict[str, Any]],
        related_summaries: list[dict[str, Any]],
        query_text: str,
        user_id: str,
        logger: logging.Logger | None = None,
    ) -> Any:
        """Own the M31E memory-packing orchestration boundary.

        The authoritative selection, ranking, rendering, and telemetry
        implementation remains chat_memory_assembly / memory_context_packer.
        CognitiveRuntime only delegates the already-existing operation.
        """

        return chat_memory_assembly.pack_chat_memory_context(
            legacy_memories=legacy_memories,
            related_summaries=related_summaries,
            query_text=query_text,
            user_id=user_id,
            logger=logger,
        )

    def record_chat_observation_fail_open(
        self,
        **kwargs: Any,
    ) -> bool:
        """Finalize the currently supported M31B observation trace.

        Trace behavior remains fail-open because the authoritative M31B
        recorder remains responsible for failure isolation.
        """

        return cognitive_trace.record_chat_observation_fail_open(
            sink=self.trace_sink,
            logger=self.logger,
            **kwargs,
        )


def create_cognitive_runtime(
    *,
    trace_logging_enabled: bool = False,
    trace_preview_policy: str = "none",
    logger: logging.Logger | None = None,
) -> CognitiveRuntime:
    """Create one lightweight runtime facade.

    No external connection is created here. The selected trace sink follows
    the existing M31B configuration semantics:
    - logging disabled -> NullTraceSink;
    - logging enabled -> LoggingTraceSink;
    - invalid preview values fail safely to ``none``.
    """

    sink = cognitive_trace.get_trace_sink(
        logging_enabled=trace_logging_enabled,
        preview_policy=trace_preview_policy,
    )

    return CognitiveRuntime(
        trace_sink=sink,
        logger=logger,
    )
