"""M31D — CognitiveRuntime facade foundation.

The runtime is a facade around existing cognitive services.

M31D established the facade. M31E incrementally moves orchestration
responsibilities through that facade without changing underlying algorithms.

Current ownership:
- delegate WorkingMemoryState lifecycle to the existing M31C builder;
- delegate cognitive trace finalization/emission to the existing M31B service;
- own trace-sink configuration for one runtime instance;
- orchestrate read-only cognitive turn-source fan-in;
- delegate life-model context retrieval to the existing life-model service;
- delegate conversation-chronology context retrieval to the existing chronology service;
- delegate memory retrieval/summary fan-in to the existing chat-memory assembly service;
- delegate memory-context packing to the existing chat-memory assembly service;
- delegate complete per-turn cognitive context assembly and model-input preparation;
- delegate foreground executive Calendar routing to existing Calendar services;
- own deterministic assistant-mode command orchestration;
- own M31F deterministic metacognitive policy + final trace sequencing;
- own M31G intrinsic salience + attention overlay before that final trace.
- own M32 habit-learning operation boundary while transport scheduling stays in chat.py.

HTTP/FastAPI serialization, Claude provider streaming, chat persistence, and
transport-bound background task scheduling remain outside CognitiveRuntime.

Dependency direction:
    chat.py -> CognitiveRuntime -> existing services

Existing services must never depend on CognitiveRuntime.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.services import assistant_mode_commands
from app.services import attention_salience
from app.services import habit_learning
from app.services import chat_memory_assembly
from app.services import cognitive_calendar_orchestration
from app.services import cognitive_trace
from app.services import cognitive_turn_context
from app.services import companion
from app.services import companion_comeback_affect
from app.services import companion_mode
from app.services import conversation_chronology
from app.services import life_model
from app.services import metacognitive_policy
from app.services import user_mood
from app.services import working_memory


COGNITIVE_RUNTIME_VERSION = "M31D-v1"


@dataclass(frozen=True)
class CognitiveTurnSources:
    life_context: dict[str, Any]
    memory_assembly: chat_memory_assembly.ChatMemoryAssembly
    detected_mode: str | None
    companion_settings_row: dict[str, Any]
    current_mood: dict[str, Any] | None
    user_mood_context: Any
    latest_briefing_for_prompt: dict[str, Any] | None


@dataclass(frozen=True)
class AssistantModeExecution:
    target_mode: str
    assistant_text: str


@dataclass(frozen=True)
class MetacognitiveTurnFinalization:
    decision: metacognitive_policy.MetacognitiveDecision
    prompt_directive: str | None
    attention_decision: attention_salience.AttentionDecision
    attention_prompt_directive: str | None
    working_state: working_memory.WorkingMemoryState
    trace_recorded: bool


@dataclass(frozen=True)
class CognitiveRuntime:
    """Facade for incrementally migrated cognitive orchestration."""

    trace_sink: cognitive_trace.TraceSink
    logger: logging.Logger | None = None
    version: str = COGNITIVE_RUNTIME_VERSION

    async def retrieve_turn_context_sources(
        self,
        *,
        user_id: str,
        user_message: str,
        conversation_id: str,
    ) -> CognitiveTurnSources:
        """Fan in read-only cognitive sources for one turn."""

        briefing_awaitable = (
            cognitive_turn_context
            .retrieve_latest_briefing_for_prompt(
                user_id
            )
            if cognitive_turn_context
            .is_briefing_discussion_request(
                user_message
            )
            else asyncio.sleep(
                0,
                result=None,
            )
        )

        (
            life_context,
            memory_assembly,
            detected_mode,
            companion_settings_row,
            current_mood,
            user_mood_context,
            latest_briefing_for_prompt,
        ) = await asyncio.gather(
            self.retrieve_life_context(
                user_id=user_id,
                mood_days=14,
            ),
            self.retrieve_chat_memory_assembly(
                user_id=user_id,
                query_text=user_message,
                conversation_id=conversation_id,
            ),
            companion_mode.detect_mode(
                user_message=user_message,
            ),
            companion.get_settings(
                user_id
            ),
            companion.get_current_mood(
                user_id
            ),
            user_mood.infer_user_mood(
                user_id,
                current_message=user_message,
            ),
            briefing_awaitable,
        )

        return CognitiveTurnSources(
            life_context=life_context,
            memory_assembly=memory_assembly,
            detected_mode=detected_mode,
            companion_settings_row=(
                companion_settings_row
                or {}
            ),
            current_mood=current_mood,
            user_mood_context=(
                user_mood_context
            ),
            latest_briefing_for_prompt=(
                latest_briefing_for_prompt
            ),
        )

    async def execute_assistant_mode_command(
        self,
        *,
        user_id: str,
        user_message: str,
        previous_mode: str,
    ) -> AssistantModeExecution | None:
        """Execute deterministic assistant-mode commands."""

        command = (
            assistant_mode_commands
            .detect_assistant_mode_command(
                user_message
            )
        )

        if command is None:
            return None

        new_mode = command.target_mode

        await companion.update_settings(
            user_id,
            assistant_mode=new_mode,
        )

        assistant_text = (
            assistant_mode_commands
            .render_mode_command_confirmation(
                command,
                previous_mode=previous_mode,
            )
        )

        return AssistantModeExecution(
            target_mode=new_mode,
            assistant_text=assistant_text,
        )

    async def evaluate_comeback_affect(
        self,
        **kwargs: Any,
    ) -> Any:
        """Delegate existing comeback-affect policy."""

        return await (
            companion_comeback_affect
            .evaluate_for_chat(
                **kwargs
            )
        )

    async def execute_calendar_turn(
        self,
        **kwargs: Any,
    ) -> cognitive_calendar_orchestration.CalendarTurnExecution:
        """Own foreground Calendar executive sequencing."""

        return await (
            cognitive_calendar_orchestration
            .execute_calendar_turn(
                logger=self.logger,
                **kwargs,
            )
        )

    async def prepare_generation_context(
        self,
        *,
        body: Any,
        user_id: str,
        context: dict[str, Any],
        chronology_context: str | None,
        assistant_mode: str,
        assistant_name: str,
        assistant_rename: str | None,
        current_mood: dict[str, Any] | None,
        user_mood_ctx: Any,
        latest_briefing_for_prompt: dict[str, Any] | None,
        comeback_affect_decision: Any,
        messages: list[dict[str, Any]],
        companion_settings_row: dict[str, Any],
        detected_mode: str | None,
        style_profile_id: str | None,
        calendar_action_result: dict[str, Any] | None,
        is_calendar_draft_action_turn: bool,
        legacy_memories: list[dict[str, Any]],
        related_summaries: list[dict[str, Any]],
        memory_assembly: chat_memory_assembly.ChatMemoryAssembly,
        turn_ref: str | None,
        logger: logging.Logger | None = None,
    ) -> cognitive_turn_context.CognitiveTurnContextAssembly:
        """Prepare complete model-facing context for one turn."""

        def pack_memory_context() -> Any:
            return self.pack_chat_memory_context(
                legacy_memories=legacy_memories,
                related_summaries=related_summaries,
                query_text=body.message,
                user_id=user_id,
                logger=logger,
            )

        def defer_trace(
            _packed_memory_context: Any,
        ) -> None:
            # M31F finalizes the single CognitiveDecisionTrace only after
            # WorkingMemoryState and deterministic metacognitive policy exist.
            return None

        return await (
            cognitive_turn_context
            .assemble_turn_context(
                body=body,
                user_id=user_id,
                context=context,
                chronology_context=(
                    chronology_context
                ),
                assistant_mode=assistant_mode,
                assistant_name=assistant_name,
                assistant_rename=assistant_rename,
                current_mood=current_mood,
                user_mood_ctx=user_mood_ctx,
                latest_briefing_for_prompt=(
                    latest_briefing_for_prompt
                ),
                comeback_affect_decision=(
                    comeback_affect_decision
                ),
                messages=messages,
                companion_settings_row=(
                    companion_settings_row
                ),
                detected_mode=detected_mode,
                style_profile_id=style_profile_id,
                calendar_action_result=(
                    calendar_action_result
                ),
                is_calendar_draft_action_turn=(
                    is_calendar_draft_action_turn
                ),
                pack_memory_context=(
                    pack_memory_context
                ),
                record_trace=defer_trace,
            )
        )

    def evaluate_metacognitive_policy(
        self,
        **kwargs: Any,
    ) -> metacognitive_policy.MetacognitiveDecision:
        """Delegate deterministic M31F policy evaluation."""

        return (
            metacognitive_policy
            .evaluate_metacognitive_policy(
                **kwargs
            )
        )

    def evaluate_attention_salience(
        self,
        **kwargs: Any,
    ) -> attention_salience.AttentionDecision:
        """Delegate deterministic M31G intrinsic salience evaluation."""

        return (
            attention_salience
            .evaluate_attention_salience(
                **kwargs
            )
        )

    def classify_habit_signal(
        self,
        user_message: str,
    ) -> habit_learning.HabitSignal:
        """Delegate deterministic M32 habit signal classification."""

        return (
            habit_learning
            .classify_habit_signal(
                user_message
            )
        )

    async def learn_habits_from_chat(
        self,
        **kwargs: Any,
    ) -> habit_learning.HabitLearningAudit:
        """Delegate M32 cross-conversation habit learning."""

        return await (
            habit_learning
            .learn_from_chat(
                **kwargs
            )
        )

    def finalize_metacognitive_turn(
        self,
        *,
        working_state: working_memory.WorkingMemoryState,
        legacy_memories: list[dict[str, Any]],
        user_message: str,
        recent_messages: list[dict[str, Any]],
        turn_ref: str | None,
        conversation_ref: str | None,
        user_ref: str | None,
        assistant_mode: str | None,
        companion_settings_row: dict[str, Any] | None,
        comeback_affect_decision: Any,
        packed_memory_context: Any,
        memory_retrieval_diagnostics: Any = None,
    ) -> MetacognitiveTurnFinalization:
        """Finalize M31F policy, prompt directive, and one-turn trace.

        Policy failures fail open to the pre-M31F behavior. Trace failures also
        remain fail open and never block generation.
        """

        try:
            decision = self.evaluate_metacognitive_policy(
                working_state=working_state,
                legacy_memories=legacy_memories,
                user_message=user_message,
                recent_messages=recent_messages,
            )
        except Exception as exc:  # noqa: BLE001
            if self.logger is not None:
                try:
                    self.logger.warning(
                        "metacognitive policy failed open: %s",
                        type(exc).__name__,
                    )
                except Exception:
                    pass

            decision = (
                metacognitive_policy
                .safe_default_decision()
            )

        prompt_directive = (
            metacognitive_policy
            .render_prompt_directive(
                decision
            )
        )

        try:
            attention_decision = (
                self.evaluate_attention_salience(
                    working_state=working_state,
                    legacy_memories=legacy_memories,
                    unverified_memory_refs=(
                        decision
                        .unverified_memory_refs
                    ),
                    response_posture=(
                        decision
                        .response_posture
                    ),
                )
            )

            attention_working_state = (
                working_memory
                .with_attention_state(
                    working_state,
                    level=(
                        attention_decision
                        .level
                    ),
                    salient_memory_refs=(
                        attention_decision
                        .salient_memory_refs
                    ),
                    attended_memory_refs=(
                        attention_decision
                        .attended_memory_refs
                    ),
                    suppressed_memory_refs=(
                        attention_decision
                        .suppressed_memory_refs
                    ),
                )
            )

            attention_prompt_directive = (
                attention_salience
                .render_prompt_directive(
                    attention_decision,
                    legacy_memories=(
                        legacy_memories
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001
            if self.logger is not None:
                try:
                    self.logger.warning(
                        "attention salience failed open: %s",
                        type(exc).__name__,
                    )
                except Exception:
                    pass

            attention_decision = (
                attention_salience
                .safe_default_decision()
            )
            attention_working_state = (
                working_state
            )
            attention_prompt_directive = None

        trace_recorded = (
            self.record_chat_observation_fail_open(
                turn_ref=turn_ref,
                conversation_ref=conversation_ref,
                user_ref=user_ref,
                assistant_mode=assistant_mode,
                companion_settings_row=(
                    companion_settings_row
                ),
                comeback_affect_decision=(
                    comeback_affect_decision
                ),
                packed_memory_context=(
                    packed_memory_context
                ),
                memory_retrieval_diagnostics=(
                    memory_retrieval_diagnostics
                ),
                legacy_memories=legacy_memories,
                metacognitive_decision=decision,
                attention_decision=(
                    attention_decision
                ),
            )
        )

        return MetacognitiveTurnFinalization(
            decision=decision,
            prompt_directive=prompt_directive,
            attention_decision=(
                attention_decision
            ),
            attention_prompt_directive=(
                attention_prompt_directive
            ),
            working_state=(
                attention_working_state
            ),
            trace_recorded=trace_recorded,
        )

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

    async def retrieve_conversation_chronology_context(
        self,
        *,
        user_id: str,
        query_text: str | None,
    ) -> str | None:
        """Own the M31E conversation-chronology context boundary.

        Detection, database lookup, and rendering remain authoritative in
        conversation_chronology. This facade only delegates orchestration.
        """

        return await conversation_chronology.build_context_if_relevant(
            user_id=user_id,
            query_text=query_text,
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
