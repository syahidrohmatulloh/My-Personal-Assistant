import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from app.services import memory
from app.services.cognitive_trace import (
    build_chat_observation_trace,
)


@dataclass(frozen=True)
class FakePackedMemory:
    memory_count: int = 1
    summary_count: int = 0
    dropped_memory_count: int = 0
    dropped_summary_count: int = 0
    total_chars: int = 120
    memory_ids: tuple[str, ...] = (
        "mem-1",
    )
    summary_ids: tuple[str, ...] = ()
    intent: str = "self_regulation"


def test_gate_skip_returns_list_compatible_diagnostics(
    monkeypatch,
) -> None:
    async def fail_embed_query(_query):
        raise AssertionError(
            "embedding must not run when gate blocks"
        )

    monkeypatch.setattr(
        memory,
        "embed_query",
        fail_embed_query,
    )

    rows = asyncio.run(
        memory.retrieve_relevant(
            "user-1",
            "cuaca besok di jakarta",
            limit=8,
        )
    )

    assert isinstance(
        rows,
        list,
    )

    assert rows == []

    diag = rows.diagnostics

    assert diag.attempted is False
    assert (
        diag.gate_reason
        == "public_current:weather"
    )
    assert diag.strategy is None
    assert (
        diag.subsystem_status
        == "not_applicable"
    )


def test_successful_retrieval_preserves_list_contract_and_metadata(
    monkeypatch,
) -> None:
    async def fake_embed_query(_query):
        return [
            0.1,
            0.2,
            0.3,
        ]

    class FakeRpc:
        def execute(self):
            return SimpleNamespace(
                data=[
                    {
                        "id": "mem-1",
                        "content":
                            "User prefers a gentle reminder "
                            "when overthinking",
                        "kind": "preference",
                        "category": "preferences",
                        "similarity": 0.72,
                        "confidence": 0.91,
                        "status": "active",
                        "archived": False,
                        "superseded": False,
                    },
                    {
                        "id": "mem-low",
                        "content": "Low similarity",
                        "kind": "context",
                        "category": "preferences",
                        "similarity": 0.10,
                        "confidence": 0.80,
                        "status": "active",
                        "archived": False,
                        "superseded": False,
                    },
                ]
            )

    class FakeSupabase:
        def rpc(
            self,
            *_args,
            **_kwargs,
        ):
            return FakeRpc()

    monkeypatch.setattr(
        memory,
        "embed_query",
        fake_embed_query,
    )

    monkeypatch.setattr(
        memory,
        "get_supabase",
        lambda: FakeSupabase(),
    )

    rows = asyncio.run(
        memory.retrieve_relevant(
            "user-1",
            "jangan overthinking",
            limit=10,
        )
    )

    assert isinstance(
        rows,
        list,
    )

    assert [
        row["id"]
        for row in rows
    ] == [
        "mem-1"
    ]

    diag = rows.diagnostics

    assert diag.attempted is True
    assert (
        diag.gate_reason
        == "personal_cue:self_regulation"
    )
    assert diag.strategy == "semantic"
    assert diag.fetched_count == 2
    assert diag.returned_count == 1
    assert diag.min_similarity == 0.40
    assert diag.latency_ms is not None
    assert (
        diag.subsystem_status
        == "healthy"
    )


def test_retrieval_diagnostics_do_not_change_row_equality() -> None:
    diagnostics = (
        memory.MemoryRetrievalDiagnostics(
            attempted=True,
            gate_reason="default_allow",
            strategy="semantic",
        )
    )

    rows = memory.MemoryRetrievalRows(
        [
            {
                "id": "m1"
            }
        ],
        diagnostics=diagnostics,
    )

    assert rows == [
        {
            "id": "m1"
        }
    ]

    assert list(rows) == [
        {
            "id": "m1"
        }
    ]


def test_memory_trace_uses_observed_values_only() -> None:
    diagnostics = (
        memory.MemoryRetrievalDiagnostics(
            attempted=True,
            gate_reason=(
                "personal_cue:self_regulation"
            ),
            strategy="semantic",
            fetched_count=3,
            returned_count=1,
            latency_ms=12.5,
            subsystem_status="healthy",
            normalized_applied=True,
            normalize_reason=(
                "self_regulation_sparse_query"
            ),
            min_similarity=0.40,
        )
    )

    trace = build_chat_observation_trace(
        turn_ref="msg-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={
            "companion_mode": "partner",
            "mood_realism": "dynamic",
        },
        comeback_affect_decision=None,
        packed_memory_context=FakePackedMemory(),
        memory_retrieval_diagnostics=diagnostics,
        legacy_memories=[
            {
                "id": "mem-1",
                "category": "preferences",
                "structured_field": None,
                "similarity": 0.72,
                "retrieval_score": 0.83,
                "confidence": 0.91,
            }
        ],
    )

    assert trace.memory is not None

    assert trace.memory.retrieval_attempted is True
    assert (
        trace.memory.retrieval_gate_reason
        == "personal_cue:self_regulation"
    )
    assert (
        trace.memory.retrieval_strategy
        == "semantic"
    )

    assert trace.memory.total_candidates == 3
    assert trace.memory.latency_ms == 12.5

    candidate = trace.memory.candidates[0]

    assert candidate.memory_ref == "mem-1"
    assert candidate.similarity_score == 0.72
    assert candidate.retrieval_score == 0.83
    assert candidate.confidence_score == 0.91

    # M31B must not reproduce private ranking logic.
    assert candidate.packing_score is None

    # Canonical salience remains an M31G concern.
    assert candidate.salience_score is None

    assert (
        candidate.selected_for_prompt
        is True
    )

    assert candidate.reason_codes == [
        "memory.retrieved.semantic_match",
        "memory.retrieved.personal_cue_threshold",
        "memory.selected.packed",
    ]


def test_embedding_failure_is_attached_as_degraded_metadata(
    monkeypatch,
) -> None:
    async def broken_embed(_query):
        raise RuntimeError(
            "provider unavailable"
        )

    monkeypatch.setattr(
        memory,
        "embed_query",
        broken_embed,
    )

    rows = asyncio.run(
        memory.retrieve_relevant(
            "user-1",
            "siapa nama anakku?",
            limit=8,
        )
    )

    assert rows == []

    assert (
        rows.diagnostics.subsystem_status
        == "degraded"
    )

    assert (
        rows.diagnostics.attempted
        is True
    )


def test_m31b_diagnostics_do_not_call_retrieval_twice(
    monkeypatch,
) -> None:
    calls = 0

    async def fake_embed_query(_query):
        nonlocal calls
        calls += 1
        return [
            0.1,
            0.2,
        ]

    class FakeRpc:
        def execute(self):
            return SimpleNamespace(
                data=[]
            )

    class FakeSupabase:
        def rpc(
            self,
            *_args,
            **_kwargs,
        ):
            return FakeRpc()

    monkeypatch.setattr(
        memory,
        "embed_query",
        fake_embed_query,
    )

    monkeypatch.setattr(
        memory,
        "get_supabase",
        lambda: FakeSupabase(),
    )

    rows = asyncio.run(
        memory.retrieve_relevant(
            "user-1",
            "ingat preferensi saya",
            limit=8,
        )
    )

    assert rows == []

    # Diagnostics come from the authoritative retrieval
    # execution rather than a duplicated shadow retrieval.
    assert calls == 1
