import asyncio
from pathlib import Path

from app.services import memory_consolidation


def _candidate():
    return memory_consolidation.ConsolidatedMemoryCandidate(
        content="User prefers concise technical answers.",
        kind="preference",
        category="preferences",
        structured_field="response_preference",
        structured_value="concise technical answers",
        confidence=0.93,
        evidence=[
            "User prefers concise technical answers.",
            "User likes concise technical answers.",
        ],
        target_memory_ref="mem-1",
        source_memory_refs=(
            "mem-1",
            "mem-2",
        ),
        reason_codes=(
            "consolidation.cluster.structured_repeat",
        ),
    )


def _target(**extra):
    row = {
        "id": "mem-1",
        "content": "User prefers concise technical answers.",
        "kind": "preference",
        "category": "preferences",
        "structured_field": "response_preference",
        "structured_value": "concise technical answers",
        "confidence": 0.93,
        "source": "auto",
        "source_priority": "explicit_user_statement",
        "evidence": [
            "User prefers concise technical answers.",
        ],
        "archived": False,
        "superseded": False,
        "status": "active",
        "deleted_at": None,
        "last_confirmed_at": None,
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def test_merge_updates_only_evidence(monkeypatch):
    captured = []

    async def fake_load_target_row(**_kwargs):
        return _target()

    async def fake_update_target_evidence(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(
        memory_consolidation,
        "_load_target_row",
        fake_load_target_row,
    )
    monkeypatch.setattr(
        memory_consolidation,
        "_update_target_evidence",
        fake_update_target_evidence,
    )

    result = asyncio.run(
        memory_consolidation.merge_candidate_evidence(
            user_id="user-1",
            candidate=_candidate(),
        )
    )

    assert result["action"] == "evidence_merged"
    assert len(captured) == 1
    assert set(captured[0]) == {
        "user_id",
        "memory_id",
        "evidence",
    }


def test_untrusted_target_is_not_mutated(monkeypatch):
    captured = []

    async def fake_load_target_row(**_kwargs):
        return _target(
            confidence=0.54,
            source_priority="repeated_pattern",
        )

    async def fake_update_target_evidence(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(
        memory_consolidation,
        "_load_target_row",
        fake_load_target_row,
    )
    monkeypatch.setattr(
        memory_consolidation,
        "_update_target_evidence",
        fake_update_target_evidence,
    )

    result = asyncio.run(
        memory_consolidation.merge_candidate_evidence(
            user_id="user-1",
            candidate=_candidate(),
        )
    )

    assert result["action"] == "target_unavailable"
    assert captured == []


def test_cycle_preserves_backward_compatible_result_keys(
    monkeypatch,
):
    async def fake_fetch(**_kwargs):
        return [
            _target(id="mem-1"),
            _target(id="mem-2"),
        ]

    captured = []

    async def fake_merge(**kwargs):
        captured.append(kwargs)
        return {
            "action": "evidence_merged",
            "memory_id": (
                kwargs["candidate"]
                .target_memory_ref
            ),
        }

    monkeypatch.setattr(
        memory_consolidation,
        "fetch_recent_active_memories",
        fake_fetch,
    )
    monkeypatch.setattr(
        memory_consolidation,
        "merge_candidate_evidence",
        fake_merge,
    )

    result = asyncio.run(
        memory_consolidation.consolidate_and_persist(
            user_id="user-1",
        )
    )

    assert result["ok"] is True
    assert result["saved"] == 0
    assert result["confirmed"] == 0
    assert result["merged"] == 1
    assert result["candidates"] == 1
    assert len(captured) == 1


def test_m33_persistence_never_changes_truth_fields():
    source = Path(
        "app/services/memory_consolidation.py"
    ).read_text(
        encoding="utf-8"
    )

    update_block = source.split(
        "async def _update_target_evidence",
        1,
    )[1].split(
        "async def merge_candidate_evidence",
        1,
    )[0]

    assert ".update(" in update_block
    assert '"evidence": evidence' in update_block

    forbidden = [
        '"confidence":',
        '"last_confirmed_at":',
        '"content":',
        '"source_priority":',
        '"archived":',
        '"superseded":',
        ".insert(",
        ".delete(",
    ]

    for token in forbidden:
        assert token not in update_block
