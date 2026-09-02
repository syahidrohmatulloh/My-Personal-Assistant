import asyncio
import inspect
from pathlib import Path

from app.services import memory
from app.services import memory_intelligence
from app.services import memory_lifecycle_governance


MIGRATION = Path(
    "schema_phase421_m35c2a_epistemic_write_contract.sql"
)


def _legacy_memory(*, kind: str, confidence: float):
    return memory.ExtractedMemory(
        content="Durable memory candidate",
        kind=kind,
        memory_key="example_key",
        memory_value="example value",
        category="preferences",
        confidence=confidence,
    )


def _candidate(*, source_priority: str):
    return memory_intelligence.CandidateMemory(
        content="User has a durable preference",
        category="preferences",
        source_priority=source_priority,
        confidence=(
            0.54
            if source_priority == "system_inference"
            else 0.90
        ),
    )


def test_schema_drops_confirmation_default_without_historical_mutation():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert (
        "alter column last_confirmed_at drop default"
        in sql
    )

    assert "update public.memories" not in sql
    assert "insert into public.memories" not in sql
    assert "delete from public.memories" not in sql
    assert "truncate" not in sql


def test_legacy_direct_user_memory_has_no_synthetic_confirmation():
    mem = _legacy_memory(
        kind="preference",
        confidence=0.92,
    )

    fields = memory._legacy_epistemic_fields(mem)

    assert (
        fields["source_priority"]
        == "explicit_user_statement"
    )
    assert fields["confidence"] == 0.92
    assert fields["last_confirmed_at"] is None


def test_legacy_assistant_plan_is_low_confidence_and_unverified():
    mem = _legacy_memory(
        kind="plan",
        confidence=0.97,
    )

    fields = memory._legacy_epistemic_fields(mem)

    assert (
        fields["source_priority"]
        == "assistant_confirmation"
    )
    assert fields["confidence"] == 0.54
    assert fields["last_confirmed_at"] is None

    lifecycle = (
        memory_lifecycle_governance
        .assess_memory_lifecycle(fields)
    )

    assert lifecycle.needs_confirmation is True
    assert lifecycle.confirmed is False


def test_only_direct_user_evidence_can_refresh_confirmation():
    allowed = {
        "explicit_user_statement",
        "user_answer_in_context",
        "user_correction",
    }

    denied = {
        "repeated_pattern",
        "assistant_confirmation",
        "system_inference",
    }

    for priority in allowed:
        assert (
            memory_intelligence
            ._candidate_can_refresh_confirmation(
                _candidate(source_priority=priority)
            )
            is True
        )

    for priority in denied:
        assert (
            memory_intelligence
            ._candidate_can_refresh_confirmation(
                _candidate(source_priority=priority)
            )
            is False
        )


def test_new_memory_intelligence_insert_explicitly_writes_null_confirmation():
    source = inspect.getsource(
        memory_intelligence._persist_candidate
    )

    assert '"last_confirmed_at": None' in source


def test_repeated_pattern_duplicate_does_not_bump_confirmation(
    monkeypatch,
):
    calls = []

    async def fake_embed_document(_content):
        return [0.1, 0.2]

    async def fake_bump(memory_id):
        calls.append(memory_id)

    monkeypatch.setattr(
        memory_intelligence,
        "embed_document",
        fake_embed_document,
    )
    monkeypatch.setattr(
        memory_intelligence,
        "_find_superseded",
        lambda **_kwargs: "existing-memory",
    )
    monkeypatch.setattr(
        memory_intelligence,
        "_bump_last_confirmed",
        fake_bump,
    )

    result = asyncio.run(
        memory_intelligence._persist_candidate(
            user_id="user-1",
            conversation_id="conversation-1",
            cand=_candidate(
                source_priority="repeated_pattern"
            ),
        )
    )

    assert result == {
        "saved": False,
        "confirmed": False,
    }
    assert calls == []


def test_explicit_user_duplicate_may_refresh_confirmation(
    monkeypatch,
):
    calls = []

    async def fake_embed_document(_content):
        return [0.1, 0.2]

    async def fake_bump(memory_id):
        calls.append(memory_id)

    monkeypatch.setattr(
        memory_intelligence,
        "embed_document",
        fake_embed_document,
    )
    monkeypatch.setattr(
        memory_intelligence,
        "_find_superseded",
        lambda **_kwargs: "existing-memory",
    )
    monkeypatch.setattr(
        memory_intelligence,
        "_bump_last_confirmed",
        fake_bump,
    )

    result = asyncio.run(
        memory_intelligence._persist_candidate(
            user_id="user-1",
            conversation_id="conversation-1",
            cand=_candidate(
                source_priority="explicit_user_statement"
            ),
        )
    )

    assert result == {
        "saved": False,
        "confirmed": True,
    }
    assert calls == ["existing-memory"]
