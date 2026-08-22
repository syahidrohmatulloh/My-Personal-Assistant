from types import SimpleNamespace

from app.services.memory_query_normalizer import normalize_memory_query


def test_self_regulation_sparse_query_is_enriched() -> None:
    decision = SimpleNamespace(
        should_retrieve=True,
        reason="personal_cue:self_regulation",
    )

    normalized = normalize_memory_query(
        "jangan overthinking",
        gate_decision=decision,
    )

    assert normalized.applied is True
    assert normalized.original == "jangan overthinking"
    assert normalized.query.startswith("jangan overthinking")
    assert "rest reminder" in normalized.query
    assert "without pressure" in normalized.query


def test_rich_self_regulation_query_is_not_overexpanded() -> None:
    decision = SimpleNamespace(
        should_retrieve=True,
        reason="personal_cue:self_regulation",
    )

    normalized = normalize_memory_query(
        "ingatkan aku istirahat kalau mulai overthinking",
        gate_decision=decision,
    )

    assert normalized.applied is False
    assert normalized.query == "ingatkan aku istirahat kalau mulai overthinking"


def test_gate_blocked_query_is_not_enriched() -> None:
    decision = SimpleNamespace(
        should_retrieve=False,
        reason="public_current:weather",
    )

    normalized = normalize_memory_query(
        "cuaca besok di jakarta",
        gate_decision=decision,
    )

    assert normalized.applied is False
    assert normalized.reason == "gate_blocked"
    assert normalized.query == "cuaca besok di jakarta"


def test_non_self_regulation_query_is_unchanged() -> None:
    decision = SimpleNamespace(
        should_retrieve=True,
        reason="default_allow",
    )

    normalized = normalize_memory_query(
        "tolong bantu susun email",
        gate_decision=decision,
    )

    assert normalized.applied is False
    assert normalized.query == "tolong bantu susun email"
