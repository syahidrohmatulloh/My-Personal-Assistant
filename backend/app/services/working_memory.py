"""M31C — ephemeral WorkingMemoryState v1.

Working memory is an in-process snapshot of already-produced turn state.

M31C boundaries:
- request/turn scoped;
- not durable memory;
- no database or external persistence;
- no hidden cache;
- no LLM-owned mutation;
- no policy authority;
- no prompt-generation authority;
- no salience computation;
- no CognitiveRuntime facade yet.

The builder mirrors values already available in the current chat runtime.
It intentionally retains metadata and internal refs rather than raw prompt,
message, memory, attachment, or calendar content.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any


WORKING_MEMORY_VERSION = "M31C-v1"


_ASSISTANT_MODES = {
    "life_companion",
    "chief_of_staff",
}

_COMPANION_MODES = {
    "professional",
    "friendly",
    "affectionate",
    "partner",
}

_MOOD_REALISM_MODES = {
    "stable",
    "dynamic",
}

_RETRIEVAL_STATUSES = {
    "healthy",
    "degraded",
    "failed",
    "not_applicable",
}


@dataclass(frozen=True)
class TurnWorkingState:
    """Identity refs for one chat turn."""

    user_ref: str | None = None
    conversation_ref: str | None = None
    turn_ref: str | None = None


@dataclass(frozen=True)
class HistoryWorkingState:
    """Metadata for the trimmed recent-history window."""

    message_count: int = 0
    is_first_message: bool = False
    load_latency_ms: float | None = None


@dataclass(frozen=True)
class ModeWorkingState:
    """Current explicit settings plus turn-level detected response mode."""

    assistant_mode: str | None = None
    detected_mode: str | None = None
    companion_mode: str | None = None
    mood_realism: str | None = None
    repair_gate_enabled: bool | None = None


@dataclass(frozen=True)
class MoodWorkingState:
    """Minimal current mood metadata.

    User mood and companion mood remain distinct state domains.
    """

    user_mood_has_data: bool | None = None
    user_mood_label: str | None = None
    user_mood_confidence: float | None = None

    companion_mood_active: bool = False
    companion_mood_label: str | None = None


@dataclass(frozen=True)
class TemporalWorkingState:
    """Browser/client time metadata already supplied to the turn."""

    timezone: str | None = None
    local_time_iso: str | None = None
    client_time_available: bool = False


@dataclass(frozen=True)
class MemoryWorkingState:
    """Current-turn retrieval and packing metadata.

    The state never recomputes retrieval ranking, packing score, or salience.
    """

    retrieval_attempted: bool | None = None
    retrieval_gate_reason: str | None = None
    retrieval_status: str | None = None

    retrieved_memory_refs: tuple[str, ...] = ()
    related_summary_refs: tuple[str, ...] = ()

    selected_memory_refs: tuple[str, ...] = ()
    selected_summary_refs: tuple[str, ...] = ()

    dropped_memory_count: int = 0
    dropped_summary_count: int = 0

    packing_intent: str | None = None
    packed_context_chars: int = 0


@dataclass(frozen=True)
class CalendarWorkingState:
    """Minimal current-turn calendar/action state.

    No event title, attendee, location, note, or other user content is retained.
    """

    draft_action_turn: bool = False
    candidate_turn: bool = False

    action_ok: bool | None = None
    confirmation_executed: bool | None = None
    candidate_saved: bool | None = None

    snapshot_dirty: bool = False


@dataclass(frozen=True)
class AttachmentWorkingState:
    """Attachment identities selected for this turn."""

    attachment_refs: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(
            self.attachment_refs
        )


@dataclass(frozen=True)
class ContextWorkingState:
    """Metadata about assembled transient context."""

    life_context_keys: tuple[str, ...] = ()

    chronology_context_present: bool = False
    pending_calendar_context_present: bool = False
    latest_briefing_present: bool = False

    volatile_context_chars: int = 0


@dataclass(frozen=True)
class WorkingMemoryState:
    """Ephemeral typed state for one request/turn."""

    version: str
    created_at_utc: datetime

    turn: TurnWorkingState = field(
        default_factory=TurnWorkingState
    )

    history: HistoryWorkingState = field(
        default_factory=HistoryWorkingState
    )

    mode: ModeWorkingState = field(
        default_factory=ModeWorkingState
    )

    mood: MoodWorkingState = field(
        default_factory=MoodWorkingState
    )

    temporal: TemporalWorkingState = field(
        default_factory=TemporalWorkingState
    )

    memory: MemoryWorkingState = field(
        default_factory=MemoryWorkingState
    )

    calendar: CalendarWorkingState = field(
        default_factory=CalendarWorkingState
    )

    attachments: AttachmentWorkingState = field(
        default_factory=AttachmentWorkingState
    )

    context: ContextWorkingState = field(
        default_factory=ContextWorkingState
    )


def _as_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = str(
        value
    ).strip()

    return text or None


def _as_optional_bool(
    value: Any,
) -> bool | None:
    if isinstance(
        value,
        bool,
    ):
        return value

    return None


def _as_optional_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _as_nonnegative_int(
    value: Any,
    *,
    default: int = 0,
) -> int:
    try:
        result = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    return max(
        0,
        result,
    )


def _mapping(
    value: Any,
) -> Mapping[str, Any]:
    if isinstance(
        value,
        Mapping,
    ):
        return value

    return {}


def _attribute(
    value: Any,
    name: str,
    default: Any = None,
) -> Any:
    if value is None:
        return default

    if isinstance(
        value,
        Mapping,
    ):
        return value.get(
            name,
            default,
        )

    return getattr(
        value,
        name,
        default,
    )


def _unique_refs(
    values: Sequence[Any] | None,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()

    for raw in (
        values
        or ()
    ):
        value = _as_text(
            raw
        )

        if (
            value
            and value not in seen
        ):
            result.append(
                value
            )
            seen.add(
                value
            )

    return tuple(
        result
    )


def _refs_from_rows(
    rows: Sequence[Any] | None,
) -> tuple[str, ...]:
    refs: list[str] = []

    for row in (
        rows
        or ()
    ):
        mapping = _mapping(
            row
        )

        ref = (
            mapping.get("id")
            or mapping.get("memory_id")
            or mapping.get("summary_id")
        )

        if ref:
            refs.append(
                str(
                    ref
                )
            )

    return _unique_refs(
        refs
    )


def _extract_user_mood_label(
    value: Any,
) -> str | None:
    data = _mapping(
        value
    )

    for key in (
        "label",
        "mood",
        "state",
        "primary_mood",
        "mood_hint",
    ):
        label = _as_text(
            data.get(
                key
            )
        )

        if label:
            return label

    for nested_key in (
        "current_message",
        "current_message_signal",
        "message_signal",
    ):
        nested = _mapping(
            data.get(
                nested_key
            )
        )

        for key in (
            "mood_hint",
            "label",
            "mood",
        ):
            label = _as_text(
                nested.get(
                    key
                )
            )

            if label:
                return label

    return None


def _extract_user_mood_confidence(
    value: Any,
) -> float | None:
    data = _mapping(
        value
    )

    direct = _as_optional_float(
        data.get(
            "confidence"
        )
    )

    if direct is not None:
        return direct

    for nested_key in (
        "current_message",
        "current_message_signal",
        "message_signal",
    ):
        nested = _mapping(
            data.get(
                nested_key
            )
        )

        confidence = _as_optional_float(
            nested.get(
                "confidence"
            )
        )

        if confidence is not None:
            return confidence

    return None


def _extract_companion_mood_label(
    value: Any,
) -> str | None:
    data = _mapping(
        value
    )

    for key in (
        "mood",
        "state",
        "label",
        "emotion",
    ):
        label = _as_text(
            data.get(
                key
            )
        )

        if label:
            return label

    return None


def _result_bool(
    value: Any,
    key: str,
) -> bool | None:
    data = _mapping(
        value
    )

    return _as_optional_bool(
        data.get(
            key
        )
    )


def _result_bool_any(
    value: Any,
    *keys: str,
) -> bool | None:
    for key in keys:
        result = _result_bool(
            value,
            key,
        )

        if result is not None:
            return result

    return None


def build_working_memory_state(
    *,
    user_ref: str | None,
    conversation_ref: str | None,
    turn_ref: str | None,

    history_message_count: int = 0,
    is_first_message: bool = False,
    history_load_latency_ms: float | None = None,

    assistant_mode: str | None = None,
    detected_mode: str | None = None,
    companion_settings_row: Mapping[str, Any] | None = None,
    current_mood: Mapping[str, Any] | None = None,
    user_mood_context: Mapping[str, Any] | None = None,

    client_context: Mapping[str, Any] | None = None,

    memory_assembly: Any = None,
    packed_memory_context: Any = None,

    calendar_draft_action_turn: bool = False,
    calendar_candidate_turn: bool = False,
    calendar_action_result: Mapping[str, Any] | None = None,
    calendar_confirmation_result: Mapping[str, Any] | None = None,
    calendar_candidate_result: Mapping[str, Any] | None = None,
    calendar_snapshot_dirty: bool = False,

    attachment_rows: Sequence[Mapping[str, Any]] | None = None,

    life_context_keys: Sequence[str] | None = None,
    chronology_context_present: bool = False,
    pending_calendar_context_present: bool = False,
    latest_briefing_present: bool = False,
    volatile_context_chars: int = 0,

    now: datetime | None = None,
) -> WorkingMemoryState:
    """Build one request-scoped WorkingMemoryState snapshot.

    Inputs are already-produced runtime results. This function performs no
    retrieval, ranking, persistence, prompt rendering, policy decision, or LLM
    call.
    """

    timestamp = (
        now
        or datetime.now(
            timezone.utc
        )
    )

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(
            tzinfo=timezone.utc
        )

    timestamp = timestamp.astimezone(
        timezone.utc
    )

    settings = _mapping(
        companion_settings_row
    )

    preferences = _mapping(
        settings.get(
            "preferences"
        )
    )

    resolved_assistant_mode = (
        _as_text(
            assistant_mode
        )
        or _as_text(
            preferences.get(
                "assistant_mode"
            )
        )
    )

    companion_mode = _as_text(
        settings.get(
            "companion_mode"
        )
    )

    mood_realism = _as_text(
        settings.get(
            "mood_realism"
        )
    )

    repair_gate_enabled = _as_optional_bool(
        settings.get(
            "repair_gate_enabled"
        )
    )

    companion_mood_active = (
        companion_mode == "partner"
        and mood_realism == "dynamic"
    )

    raw_client_context = _mapping(
        client_context
    )

    timezone_name = _as_text(
        raw_client_context.get(
            "timezone"
        )
        or raw_client_context.get(
            "time_zone"
        )
    )

    local_time_iso = _as_text(
        raw_client_context.get(
            "local_time"
        )
        or raw_client_context.get(
            "local_datetime"
        )
        or raw_client_context.get(
            "now"
        )
    )

    legacy_memories = _attribute(
        memory_assembly,
        "legacy_memories",
        (),
    )

    related_summaries = _attribute(
        memory_assembly,
        "related_summaries",
        (),
    )

    retrieval_diagnostics = _attribute(
        memory_assembly,
        "memory_retrieval_diagnostics",
        None,
    )

    retrieval_attempted = _as_optional_bool(
        _attribute(
            retrieval_diagnostics,
            "attempted",
            None,
        )
    )

    retrieval_gate_reason = _as_text(
        _attribute(
            retrieval_diagnostics,
            "gate_reason",
            None,
        )
    )

    retrieval_status = _as_text(
        _attribute(
            retrieval_diagnostics,
            "subsystem_status",
            None,
        )
    )

    selected_memory_refs = _unique_refs(
        _attribute(
            packed_memory_context,
            "memory_ids",
            (),
        )
    )

    selected_summary_refs = _unique_refs(
        _attribute(
            packed_memory_context,
            "summary_ids",
            (),
        )
    )

    state = WorkingMemoryState(
        version=WORKING_MEMORY_VERSION,
        created_at_utc=timestamp,

        turn=TurnWorkingState(
            user_ref=_as_text(
                user_ref
            ),
            conversation_ref=_as_text(
                conversation_ref
            ),
            turn_ref=_as_text(
                turn_ref
            ),
        ),

        history=HistoryWorkingState(
            message_count=_as_nonnegative_int(
                history_message_count
            ),
            is_first_message=bool(
                is_first_message
            ),
            load_latency_ms=_as_optional_float(
                history_load_latency_ms
            ),
        ),

        mode=ModeWorkingState(
            assistant_mode=resolved_assistant_mode,
            detected_mode=_as_text(
                detected_mode
            ),
            companion_mode=companion_mode,
            mood_realism=mood_realism,
            repair_gate_enabled=repair_gate_enabled,
        ),

        mood=MoodWorkingState(
            user_mood_has_data=_as_optional_bool(
                _mapping(
                    user_mood_context
                ).get(
                    "has_data"
                )
            ),
            user_mood_label=_extract_user_mood_label(
                user_mood_context
            ),
            user_mood_confidence=_extract_user_mood_confidence(
                user_mood_context
            ),
            companion_mood_active=companion_mood_active,
            companion_mood_label=_extract_companion_mood_label(
                current_mood
            ),
        ),

        temporal=TemporalWorkingState(
            timezone=timezone_name,
            local_time_iso=local_time_iso,
            client_time_available=bool(
                local_time_iso
            ),
        ),

        memory=MemoryWorkingState(
            retrieval_attempted=retrieval_attempted,
            retrieval_gate_reason=retrieval_gate_reason,
            retrieval_status=retrieval_status,

            retrieved_memory_refs=_refs_from_rows(
                legacy_memories
            ),
            related_summary_refs=_refs_from_rows(
                related_summaries
            ),

            selected_memory_refs=selected_memory_refs,
            selected_summary_refs=selected_summary_refs,

            dropped_memory_count=_as_nonnegative_int(
                _attribute(
                    packed_memory_context,
                    "dropped_memory_count",
                    0,
                )
            ),
            dropped_summary_count=_as_nonnegative_int(
                _attribute(
                    packed_memory_context,
                    "dropped_summary_count",
                    0,
                )
            ),

            packing_intent=_as_text(
                _attribute(
                    packed_memory_context,
                    "intent",
                    None,
                )
            ),

            packed_context_chars=_as_nonnegative_int(
                _attribute(
                    packed_memory_context,
                    "total_chars",
                    0,
                )
            ),
        ),

        calendar=CalendarWorkingState(
            draft_action_turn=bool(
                calendar_draft_action_turn
            ),
            candidate_turn=bool(
                calendar_candidate_turn
            ),
            action_ok=_result_bool_any(
                calendar_action_result,
                "ok",
                "success",
            ),
            confirmation_executed=_result_bool(
                calendar_confirmation_result,
                "executed",
            ),
            candidate_saved=_result_bool(
                calendar_candidate_result,
                "saved",
            ),
            snapshot_dirty=bool(
                calendar_snapshot_dirty
            ),
        ),

        attachments=AttachmentWorkingState(
            attachment_refs=_refs_from_rows(
                attachment_rows
            ),
        ),

        context=ContextWorkingState(
            life_context_keys=_unique_refs(
                life_context_keys
            ),
            chronology_context_present=bool(
                chronology_context_present
            ),
            pending_calendar_context_present=bool(
                pending_calendar_context_present
            ),
            latest_briefing_present=bool(
                latest_briefing_present
            ),
            volatile_context_chars=_as_nonnegative_int(
                volatile_context_chars
            ),
        ),
    )

    validate_working_memory_state(
        state
    )

    return state


def validate_working_memory_state(
    state: WorkingMemoryState,
) -> None:
    """Validate the M31C v1 contract without changing state."""

    if state.version != WORKING_MEMORY_VERSION:
        raise ValueError(
            f"Unsupported working-memory version: {state.version}"
        )

    if state.created_at_utc.tzinfo is None:
        raise ValueError(
            "created_at_utc must be timezone-aware"
        )

    if (
        state.mode.assistant_mode is not None
        and state.mode.assistant_mode
        not in _ASSISTANT_MODES
    ):
        raise ValueError(
            "Invalid assistant_mode"
        )

    if (
        state.mode.companion_mode is not None
        and state.mode.companion_mode
        not in _COMPANION_MODES
    ):
        raise ValueError(
            "Invalid companion_mode"
        )

    if (
        state.mode.mood_realism is not None
        and state.mode.mood_realism
        not in _MOOD_REALISM_MODES
    ):
        raise ValueError(
            "Invalid mood_realism"
        )

    if (
        state.memory.retrieval_status is not None
        and state.memory.retrieval_status
        not in _RETRIEVAL_STATUSES
    ):
        raise ValueError(
            "Invalid retrieval_status"
        )

    nonnegative_values = (
        state.history.message_count,
        state.memory.dropped_memory_count,
        state.memory.dropped_summary_count,
        state.memory.packed_context_chars,
        state.attachments.count,
        state.context.volatile_context_chars,
    )

    if any(
        value < 0
        for value in nonnegative_values
    ):
        raise ValueError(
            "Working-memory counts must be nonnegative"
        )


def working_memory_metadata_dict(
    state: WorkingMemoryState,
) -> dict[str, Any]:
    """Return a metadata-only primitive view for tests/inspection.

    This is not a persistence format and is not automatically logged.
    """

    validate_working_memory_state(
        state
    )

    def convert(
        value: Any,
    ) -> Any:
        if isinstance(
            value,
            datetime,
        ):
            return (
                value.astimezone(
                    timezone.utc
                )
                .isoformat()
                .replace(
                    "+00:00",
                    "Z",
                )
            )

        if is_dataclass(
            value
        ):
            return {
                item.name: convert(
                    getattr(
                        value,
                        item.name,
                    )
                )
                for item in fields(
                    value
                )
            }

        if isinstance(
            value,
            tuple,
        ):
            return [
                convert(
                    item
                )
                for item in value
            ]

        if isinstance(
            value,
            list,
        ):
            return [
                convert(
                    item
                )
                for item in value
            ]

        if isinstance(
            value,
            dict,
        ):
            return {
                str(key): convert(
                    nested
                )
                for key, nested in value.items()
            }

        return value

    return convert(
        state
    )
