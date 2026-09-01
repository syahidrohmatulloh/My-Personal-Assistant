import inspect
from datetime import datetime, timezone
from pathlib import Path

from app.services import attention_salience
from app.services import working_memory


def _state(
    *selected_refs: str,
) -> working_memory.WorkingMemoryState:
    return working_memory.WorkingMemoryState(
        version=working_memory.WORKING_MEMORY_VERSION,
        created_at_utc=datetime(
            2026,
            9,
            1,
            8,
            0,
            tzinfo=timezone.utc,
        ),
        memory=working_memory.MemoryWorkingState(
            selected_memory_refs=tuple(
                selected_refs
            )
        ),
    )


def _row(
    memory_ref: str,
    *,
    category: str,
    structured_field: str | None = None,
    salience=None,
    content: str | None = None,
    **extra,
):
    row = {
        "id": memory_ref,
        "category": category,
        "content": (
            content
            or f"Memory {memory_ref}"
        ),
    }

    if structured_field is not None:
        row["structured_field"] = structured_field

    if salience is not None:
        row["salience"] = salience

    row.update(extra)
    return row


def _candidate(
    decision,
    ref: str,
):
    return next(
        candidate
        for candidate in decision.candidates
        if candidate.memory_ref == ref
    )


def test_version_and_safe_default() -> None:
    decision = (
        attention_salience
        .safe_default_decision()
    )

    assert (
        decision.version
        == "M31G-v1"
    )
    assert decision.level == "normal"
    assert decision.candidates == ()
    assert (
        decision.attended_memory_refs
        == ()
    )
    assert (
        "attention.salience.fallback.safe_default"
        in decision.reason_codes
    )


def test_service_api_accepts_no_query_axis() -> None:
    params = set(
        inspect.signature(
            attention_salience
            .evaluate_attention_salience
        ).parameters
    )

    assert "query_text" not in params
    assert "user_message" not in params
    assert "similarity" not in params
    assert "retrieval_score" not in params


def test_scores_only_already_selected_memories() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "mem-1"
            ),
            legacy_memories=[
                _row(
                    "mem-1",
                    category="identity",
                ),
                _row(
                    "mem-2",
                    category="important_dates",
                ),
            ],
        )
    )

    assert [
        candidate.memory_ref
        for candidate in decision.candidates
    ] == [
        "mem-1"
    ]


def test_salience_is_independent_of_confidence_and_relevance_scores() -> None:
    state = _state(
        "mem-1"
    )

    baseline = (
        attention_salience
        .evaluate_attention_salience(
            working_state=state,
            legacy_memories=[
                _row(
                    "mem-1",
                    category="goals",
                    confidence=0.10,
                    similarity=0.20,
                    retrieval_score=0.30,
                    source_priority="assistant_confirmation",
                    created_at="2019-01-01T00:00:00Z",
                )
            ],
        )
    )

    changed = (
        attention_salience
        .evaluate_attention_salience(
            working_state=state,
            legacy_memories=[
                _row(
                    "mem-1",
                    category="goals",
                    confidence=0.99,
                    similarity=0.99,
                    retrieval_score=9.99,
                    source_priority="user_correction",
                    created_at="2026-09-01T00:00:00Z",
                    last_confirmed_at="2026-09-01T00:00:00Z",
                )
            ],
        )
    )

    assert (
        _candidate(
            baseline,
            "mem-1",
        ).score
        == _candidate(
            changed,
            "mem-1",
        ).score
        == 0.60
    )


def test_category_salience_tiers_are_deterministic() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "date",
                "constraint",
                "goal",
                "context",
            ),
            legacy_memories=[
                _row(
                    "date",
                    category="important_dates",
                ),
                _row(
                    "constraint",
                    category="constraints",
                ),
                _row(
                    "goal",
                    category="goals",
                ),
                _row(
                    "context",
                    category="context",
                ),
            ],
        )
    )

    assert _candidate(
        decision,
        "date",
    ).score == 0.78

    assert _candidate(
        decision,
        "date",
    ).tier == "high"

    assert _candidate(
        decision,
        "constraint",
    ).score == 0.74

    assert _candidate(
        decision,
        "goal",
    ).score == 0.60

    assert _candidate(
        decision,
        "goal",
    ).tier == "medium"

    assert _candidate(
        decision,
        "context",
    ).score == 0.32

    assert _candidate(
        decision,
        "context",
    ).tier == "low"


def test_core_structured_field_can_raise_core_memory_to_high() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "spouse"
            ),
            legacy_memories=[
                _row(
                    "spouse",
                    category="relationships",
                    structured_field="spouse_name",
                )
            ],
        )
    )

    candidate = _candidate(
        decision,
        "spouse",
    )

    assert candidate.score == 0.78
    assert candidate.tier == "high"
    assert (
        "attention.salience.structured.core_field"
        in candidate.reason_codes
    )


def test_other_structured_field_gets_small_intrinsic_bonus() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "project"
            ),
            legacy_memories=[
                _row(
                    "project",
                    category="projects",
                    structured_field="project_codename",
                )
            ],
        )
    )

    candidate = _candidate(
        decision,
        "project",
    )

    assert candidate.score == 0.58
    assert candidate.tier == "medium"
    assert (
        "attention.salience.structured.other_field"
        in candidate.reason_codes
    )


def test_legacy_optional_salience_field_does_not_override_canonical_m31g() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "pref",
                "date",
            ),
            legacy_memories=[
                _row(
                    "pref",
                    category="preferences",
                    salience=9,
                ),
                _row(
                    "date",
                    category="important_dates",
                    salience=0.10,
                ),
            ],
        )
    )

    # memory.py has a legacy optional `salience` ranking hint.
    # M31G does not relabel that implementation field as canonical salience.
    assert _candidate(
        decision,
        "pref",
    ).score == 0.48

    assert _candidate(
        decision,
        "date",
    ).score == 0.78


def test_attention_chooses_top_two_salient_selected_memories() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "goal",
                "identity",
                "date",
            ),
            legacy_memories=[
                _row(
                    "goal",
                    category="goals",
                ),
                _row(
                    "identity",
                    category="identity",
                    structured_field="preferred_name",
                ),
                _row(
                    "date",
                    category="important_dates",
                ),
            ],
        )
    )

    assert decision.level == "high"
    assert (
        decision.salient_memory_refs
        == (
            "identity",
            "date",
            "goal",
        )
    )
    assert (
        decision.attended_memory_refs
        == (
            "identity",
            "date",
        )
    )


def test_unverified_memory_keeps_salience_but_is_suppressed_from_attention() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "identity",
                "date",
            ),
            legacy_memories=[
                _row(
                    "identity",
                    category="identity",
                    structured_field="preferred_name",
                ),
                _row(
                    "date",
                    category="important_dates",
                ),
            ],
            unverified_memory_refs=(
                "identity",
            ),
        )
    )

    assert _candidate(
        decision,
        "identity",
    ).score == 0.78

    assert (
        decision.suppressed_memory_refs
        == (
            "identity",
        )
    )

    assert (
        decision.attended_memory_refs
        == (
            "date",
        )
    )

    assert (
        "attention.focus.suppressed_unverified"
        in decision.reason_codes
    )


def test_clarify_posture_suppresses_attention_without_erasing_salience() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "date"
            ),
            legacy_memories=[
                _row(
                    "date",
                    category="important_dates",
                )
            ],
            response_posture="clarify",
        )
    )

    assert _candidate(
        decision,
        "date",
    ).score == 0.78

    assert (
        decision.salient_memory_refs
        == (
            "date",
        )
    )
    assert (
        decision.attended_memory_refs
        == ()
    )
    assert (
        decision.suppressed_memory_refs
        == (
            "date",
        )
    )
    assert decision.level == "normal"
    assert (
        "attention.focus.suppressed_clarify"
        in decision.reason_codes
    )


def test_all_low_salience_selected_memory_keeps_attention_normal() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "context"
            ),
            legacy_memories=[
                _row(
                    "context",
                    category="context",
                )
            ],
        )
    )

    assert decision.level == "normal"
    assert (
        decision.salient_memory_refs
        == ()
    )
    assert (
        decision.attended_memory_refs
        == ()
    )


def test_prompt_directive_contains_attended_content_but_no_internal_refs() -> None:
    decision = (
        attention_salience
        .evaluate_attention_salience(
            working_state=_state(
                "date",
                "identity",
            ),
            legacy_memories=[
                _row(
                    "date",
                    category="important_dates",
                    content="Board presentation is on 15 September.",
                ),
                _row(
                    "identity",
                    category="identity",
                    structured_field="preferred_name",
                    content="The user prefers to be called Beb.",
                ),
            ],
            unverified_memory_refs=(
                "identity",
            ),
        )
    )

    directive = (
        attention_salience
        .render_prompt_directive(
            decision,
            legacy_memories=[
                _row(
                    "date",
                    category="important_dates",
                    content="Board presentation is on 15 September.",
                ),
                _row(
                    "identity",
                    category="identity",
                    structured_field="preferred_name",
                    content="The user prefers to be called Beb.",
                ),
            ],
        )
    )

    assert directive is not None
    assert (
        "Board presentation is on 15 September."
        in directive
    )
    assert (
        "The user prefers to be called Beb."
        not in directive
    )
    assert "date" not in directive
    assert "identity" not in directive
    assert "salience scores" in directive


def test_service_has_no_llm_db_embedding_or_network_dependency() -> None:
    source = Path(
        "app/services/attention_salience.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    forbidden = [
        "get_claude",
        "get_supabase",
        "embed_query",
        "embed_document",
        ".table(",
        ".rpc(",
        "anthropic",
        "httpx",
        "requests.",
    ]

    for token in forbidden:
        assert token not in source
