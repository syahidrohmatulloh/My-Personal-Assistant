from __future__ import annotations

import asyncio

from app.services import habit_learning


def _candidate() -> habit_learning.HabitCandidate:
    return habit_learning.HabitCandidate(
        activity="lari pagi",
        signature="lari pagi",
        structured_field=(
            habit_learning._pattern_ref(
                "lari pagi"
            )
        ),
        observation_count=5,
        distinct_days=4,
        span_days=14,
        confidence=0.50,
        evidence=(
            "Aku baru selesai lari pagi",
            "Aku habis lari pagi",
        ),
    )


def test_inserted_habit_payload_is_qualified_inferred_memory(
    monkeypatch,
) -> None:
    captured = {}

    monkeypatch.setattr(
        habit_learning,
        "_fetch_existing_routine_rows",
        lambda **_kwargs: [],
    )

    async def fake_embed(text):
        captured["embed_text"] = text
        return [0.1, 0.2]

    monkeypatch.setattr(
        habit_learning,
        "embed_document",
        fake_embed,
    )

    def fake_insert(payload):
        captured["payload"] = payload
        return "mem-new"

    monkeypatch.setattr(
        habit_learning,
        "_insert_memory_row",
        fake_insert,
    )

    action, memory_id = asyncio.run(
        habit_learning.persist_habit_candidate(
            user_id="user-1",
            conversation_id="conv-1",
            candidate=_candidate(),
        )
    )

    assert action == "inserted_inferred"
    assert memory_id == "mem-new"

    payload = captured["payload"]

    assert payload["category"] == "routines"
    assert payload["kind"] == "context"
    assert (
        payload["source_priority"]
        == "repeated_pattern"
    )
    assert payload["source"] == "auto"
    assert payload["confidence"] < 0.55
    assert payload["structured_field"].startswith(
        "habit_pattern_"
    )
    assert "appears to have" in payload["content"]
    assert payload["evidence"]
    assert payload["last_confirmed_at"] is None
    assert payload["last_user_confirmed_at"] is None


def test_existing_m32_inference_is_refreshed_without_confirmation(
    monkeypatch,
) -> None:
    candidate = _candidate()
    updates = []

    monkeypatch.setattr(
        habit_learning,
        "_fetch_existing_routine_rows",
        lambda **_kwargs: [
            {
                "id": "mem-existing",
                "source": "auto",
                "source_priority": "repeated_pattern",
                "category": "routines",
                "structured_field": (
                    candidate.structured_field
                ),
                "structured_value": "lari pagi",
                "confidence": 0.49,
                "evidence": [
                    "older evidence"
                ],
                "last_confirmed_at": None,
            }
        ],
    )

    def fake_update(**kwargs):
        updates.append(kwargs)

    monkeypatch.setattr(
        habit_learning,
        "_update_memory_row",
        fake_update,
    )

    action, memory_id = asyncio.run(
        habit_learning.persist_habit_candidate(
            user_id="user-1",
            conversation_id="conv-1",
            candidate=candidate,
        )
    )

    assert action == "refreshed_inferred"
    assert memory_id == "mem-existing"
    assert len(updates) == 1

    payload = updates[0]["payload"]
    assert payload["confidence"] < 0.55
    assert "last_confirmed_at" not in payload
    assert "older evidence" in payload["evidence"]


def test_explicit_memory_with_same_pattern_field_is_preserved(
    monkeypatch,
) -> None:
    candidate = _candidate()

    monkeypatch.setattr(
        habit_learning,
        "_fetch_existing_routine_rows",
        lambda **_kwargs: [
            {
                "id": "mem-explicit",
                "source": "auto",
                "source_priority": (
                    "explicit_user_statement"
                ),
                "category": "routines",
                "structured_field": (
                    candidate.structured_field
                ),
                "structured_value": "lari pagi",
                "confidence": 0.95,
            }
        ],
    )

    async def fail_embed(_text):
        raise AssertionError(
            "explicit memory must prevent inferred insert"
        )

    monkeypatch.setattr(
        habit_learning,
        "embed_document",
        fail_embed,
    )

    action, memory_id = asyncio.run(
        habit_learning.persist_habit_candidate(
            user_id="user-1",
            conversation_id="conv-1",
            candidate=candidate,
        )
    )

    assert (
        action
        == "explicit_existing_preserved"
    )
    assert memory_id == "mem-explicit"


def test_explicit_routine_value_is_preserved_even_with_other_field(
    monkeypatch,
) -> None:
    candidate = _candidate()

    monkeypatch.setattr(
        habit_learning,
        "_fetch_existing_routine_rows",
        lambda **_kwargs: [
            {
                "id": "mem-user-routine",
                "source": "auto",
                "source_priority": (
                    "user_correction"
                ),
                "category": "routines",
                "structured_field": "morning_activity",
                "structured_value": "lari pagi",
                "confidence": 0.95,
            }
        ],
    )

    async def fail_embed(_text):
        raise AssertionError(
            "user-authored routine must be preserved"
        )

    monkeypatch.setattr(
        habit_learning,
        "embed_document",
        fail_embed,
    )

    action, memory_id = asyncio.run(
        habit_learning.persist_habit_candidate(
            user_id="user-1",
            conversation_id="conv-1",
            candidate=candidate,
        )
    )

    assert (
        action
        == "explicit_existing_preserved"
    )
    assert memory_id == "mem-user-routine"


def test_embedding_failure_does_not_create_unretrievable_memory(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        habit_learning,
        "_fetch_existing_routine_rows",
        lambda **_kwargs: [],
    )

    async def fail_embed(_text):
        raise RuntimeError(
            "simulated"
        )

    monkeypatch.setattr(
        habit_learning,
        "embed_document",
        fail_embed,
    )

    monkeypatch.setattr(
        habit_learning,
        "_insert_memory_row",
        lambda _payload: (
            (_ for _ in ()).throw(
                AssertionError(
                    "must not insert without embedding"
                )
            )
        ),
    )

    action, memory_id = asyncio.run(
        habit_learning.persist_habit_candidate(
            user_id="user-1",
            conversation_id="conv-1",
            candidate=_candidate(),
        )
    )

    assert action == "embedding_failed"
    assert memory_id is None


def test_explicit_correction_supersedes_only_m32_inference(
    monkeypatch,
) -> None:
    observation = (
        habit_learning
        .parse_explicit_correction(
            "Aku sudah tidak lari pagi lagi"
        )
    )
    assert observation is not None

    field = habit_learning._pattern_ref(
        observation.signature
    )

    updates = []

    monkeypatch.setattr(
        habit_learning,
        "_fetch_existing_routine_rows",
        lambda **_kwargs: [
            {
                "id": "explicit",
                "source": "manual",
                "source_priority": (
                    "explicit_user_statement"
                ),
                "category": "routines",
                "structured_field": field,
            },
            {
                "id": "inferred",
                "source": "auto",
                "source_priority": "repeated_pattern",
                "category": "routines",
                "structured_field": field,
            },
        ],
    )

    monkeypatch.setattr(
        habit_learning,
        "_update_memory_row",
        lambda **kwargs: updates.append(
            kwargs
        ),
    )

    action, memory_id = asyncio.run(
        habit_learning.supersede_inferred_habit(
            user_id="user-1",
            observation=observation,
        )
    )

    assert (
        action
        == "superseded_by_user_correction"
    )
    assert memory_id == "inferred"
    assert len(updates) == 1
    assert (
        updates[0]["memory_id"]
        == "inferred"
    )
    assert (
        updates[0]["payload"]["superseded"]
        is True
    )
    assert (
        updates[0]["payload"]["status"]
        == "superseded"
    )
    assert (
        "superseded_at"
        in updates[0]["payload"]
    )
    assert (
        "archived"
        not in updates[0]["payload"]
    )
    assert (
        "archived_by"
        not in updates[0]["payload"]
    )


def test_correction_does_not_touch_explicit_only_memory(
    monkeypatch,
) -> None:
    observation = (
        habit_learning
        .parse_explicit_correction(
            "I stopped yoga"
        )
    )
    assert observation is not None

    monkeypatch.setattr(
        habit_learning,
        "_fetch_existing_routine_rows",
        lambda **_kwargs: [
            {
                "id": "explicit",
                "source": "manual",
                "source_priority": (
                    "explicit_user_statement"
                ),
                "category": "routines",
                "structured_field": (
                    habit_learning._pattern_ref(
                        observation.signature
                    )
                ),
            }
        ],
    )

    monkeypatch.setattr(
        habit_learning,
        "_update_memory_row",
        lambda **_kwargs: (
            (_ for _ in ()).throw(
                AssertionError(
                    "explicit memory must not be superseded"
                )
            )
        ),
    )

    action, memory_id = asyncio.run(
        habit_learning.supersede_inferred_habit(
            user_id="user-1",
            observation=observation,
        )
    )

    assert (
        action
        == "no_matching_inferred_pattern"
    )
    assert memory_id is None


def test_learning_fail_open_returns_safe_audit(
    monkeypatch,
) -> None:
    async def fail_history(**_kwargs):
        raise RuntimeError(
            "simulated history failure"
        )

    monkeypatch.setattr(
        habit_learning,
        "fetch_recent_user_messages",
        fail_history,
    )

    audit = asyncio.run(
        habit_learning.learn_from_chat(
            user_id="user-1",
            conversation_id="conv-1",
            user_message=(
                "Aku baru selesai lari pagi"
            ),
        )
    )

    assert audit.attempted is True
    assert audit.action == "history_unavailable"
    assert (
        "habit.history.unavailable"
        in audit.reason_codes
    )


def test_confirmed_repeated_pattern_is_never_downgraded(
    monkeypatch,
) -> None:
    candidate = _candidate()

    monkeypatch.setattr(
        habit_learning,
        "_fetch_existing_routine_rows",
        lambda **_kwargs: [
            {
                "id": "confirmed",
                "source": "auto",
                "source_priority": "repeated_pattern",
                "category": "routines",
                "structured_field": candidate.structured_field,
                "structured_value": candidate.activity,
                "confidence": 0.82,
                "last_confirmed_at": "2026-08-01T00:00:00Z",
                "last_user_confirmed_at": "2026-08-20T00:00:00Z",
            }
        ],
    )

    monkeypatch.setattr(
        habit_learning,
        "_update_memory_row",
        lambda **_kwargs: (
            (_ for _ in ()).throw(
                AssertionError(
                    "confirmed memory must not be downgraded"
                )
            )
        ),
    )

    action, memory_id = asyncio.run(
        habit_learning.persist_habit_candidate(
            user_id="user-1",
            conversation_id="conv-1",
            candidate=candidate,
        )
    )

    assert action == "explicit_existing_preserved"
    assert memory_id == "confirmed"
