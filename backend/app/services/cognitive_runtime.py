"""M31D — CognitiveRuntime facade foundation.

The runtime is a facade around existing cognitive services.

M31D-1 intentionally does NOT move retrieval, context packing, calendar
routing, prompt assembly, LLM generation, or persistence out of chat.py.

Initial ownership:
- delegate WorkingMemoryState lifecycle to the existing M31C builder;
- delegate cognitive trace finalization/emission to the existing M31B service;
- own trace-sink configuration for one runtime instance.

Dependency direction:
    chat.py -> CognitiveRuntime -> existing services

Existing services must never depend on CognitiveRuntime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services import cognitive_trace
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
