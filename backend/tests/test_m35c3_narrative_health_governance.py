from __future__ import annotations

import inspect

from app.services import memory_health_scheduler
from app.services import memory_narrative_summary


def _memory(
    *,
    memory_id: str,
    content: str,
    source_priority: str,
    last_user_confirmed_at=None,
    last_confirmed_at=None,
    archived=False,
    superseded=False,
    status="active",
    deleted_at=None,
):
    return {
        "id": memory_id,
        "user_id": "user-1",
        "content": content,
        "kind": "fact",
        "category": "identity",
        "structured_field": f"field_{memory_id}",
        "structured_value": content,
        "source": "auto",
        "source_priority": source_priority,
        "confidence": 0.54,
        "evidence": [],
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-02T00:00:00+00:00",
        "last_confirmed_at": last_confirmed_at,
        "last_user_confirmed_at": last_user_confirmed_at,
        "archived": archived,
        "superseded": superseded,
        "status": status,
        "deleted_at": deleted_at,
    }


def test_direct_user_provenance_is_narrative_authority():
    for source_priority in (
        "explicit_user_statement",
        "user_answer_in_context",
        "user_correction",
    ):
        row = _memory(
            memory_id=source_priority,
            content="Direct user fact",
            source_priority=source_priority,
        )

        assert (
            memory_narrative_summary
            ._is_authoritative_memory(row)
            is True
        )


def test_canonical_confirmation_can_upgrade_weak_provenance():
    row = _memory(
        memory_id="canonical",
        content="Confirmed fact",
        source_priority="system_inference",
        last_user_confirmed_at=(
            "2026-09-05T00:00:00+00:00"
        ),
    )

    assert (
        memory_narrative_summary
        ._is_authoritative_memory(row)
        is True
    )


def test_legacy_confirmation_does_not_upgrade_weak_provenance():
    row = _memory(
        memory_id="legacy",
        content="Legacy weak fact",
        source_priority="system_inference",
        last_confirmed_at=(
            "2026-09-05T00:00:00+00:00"
        ),
    )

    assert (
        memory_narrative_summary
        ._is_authoritative_memory(row)
        is False
    )


def test_unverified_inference_is_excluded_from_authoritative_rows():
    rows = [
        _memory(
            memory_id="direct",
            content="User directly stated this",
            source_priority="explicit_user_statement",
        ),
        _memory(
            memory_id="inferred",
            content="Machine inferred biography",
            source_priority="system_inference",
        ),
        _memory(
            memory_id="repeat",
            content="Repeated pattern biography",
            source_priority="repeated_pattern",
        ),
        _memory(
            memory_id="legacy",
            content="Legacy unknown biography",
            source_priority="legacy_unknown",
            last_confirmed_at=(
                "2026-09-05T00:00:00+00:00"
            ),
        ),
    ]

    authoritative = (
        memory_narrative_summary
        ._authoritative_rows(rows)
    )

    assert [
        row["id"]
        for row in authoritative
    ] == ["direct"]


def test_authoritative_source_hash_is_order_stable():
    first = _memory(
        memory_id="a",
        content="User likes tea",
        source_priority="explicit_user_statement",
    )
    second = _memory(
        memory_id="b",
        content="User lives in Jakarta",
        source_priority="user_answer_in_context",
    )

    hash_ab = (
        memory_narrative_summary
        ._authoritative_source_hash(
            [first, second]
        )
    )
    hash_ba = (
        memory_narrative_summary
        ._authoritative_source_hash(
            [second, first]
        )
    )

    assert hash_ab == hash_ba
    assert len(hash_ab) == 16

    changed = dict(second)
    changed["content"] = (
        "User lives in Bandung"
    )

    changed_hash = (
        memory_narrative_summary
        ._authoritative_source_hash(
            [first, changed]
        )
    )

    assert changed_hash != hash_ab


def test_weak_rows_do_not_change_authoritative_source_hash():
    direct = _memory(
        memory_id="direct",
        content="User likes tea",
        source_priority="explicit_user_statement",
    )

    weak = _memory(
        memory_id="weak",
        content="Machine inferred coffee",
        source_priority="system_inference",
    )

    base_hash = (
        memory_narrative_summary
        ._authoritative_source_hash(
            [direct]
        )
    )

    with_weak_hash = (
        memory_narrative_summary
        ._authoritative_source_hash(
            [direct, weak]
        )
    )

    assert base_hash == with_weak_hash


def test_persisted_source_token_requires_current_governance():
    source_hash = "0123456789abcdef"

    encoded = (
        memory_narrative_summary
        ._encode_persisted_source(
            "llm",
            source_hash,
        )
    )

    decoded = (
        memory_narrative_summary
        ._decode_persisted_source(
            encoded
        )
    )

    assert decoded == {
        "source": "llm",
        "governance_version": "m35c3-v1",
        "source_hash": source_hash,
    }

    assert (
        memory_narrative_summary
        ._decode_persisted_source(
            "llm"
        )
        is None
    )

    assert (
        memory_narrative_summary
        ._decode_persisted_source(
            "l|old-governance|"
            "0123456789abcdef"
        )
        is None
    )


def test_deterministic_narrative_counts_authority_only():
    direct = _memory(
        memory_id="direct",
        content="User enjoys long walks",
        source_priority="explicit_user_statement",
    )

    weak = _memory(
        memory_id="weak",
        content="Machine inferred hidden biography",
        source_priority="system_inference",
    )

    payload = (
        memory_narrative_summary
        ._deterministic_summary(
            [direct, weak]
        )
    )

    assert payload["memory_count"] == 1
    assert (
        payload["governance_version"]
        == "m35c3-v1"
    )
    assert len(payload["source_hash"]) == 16


def test_llm_brief_excludes_unverified_inference():
    direct = _memory(
        memory_id="direct",
        content="User enjoys long walks",
        source_priority="explicit_user_statement",
    )

    weak = _memory(
        memory_id="weak",
        content="Machine inferred hidden biography",
        source_priority="system_inference",
    )

    brief = (
        memory_narrative_summary
        ._memory_brief_for_prompt(
            [direct, weak]
        )
    )

    assert "User enjoys long walks" in brief
    assert (
        "Machine inferred hidden biography"
        not in brief
    )


def test_persisted_summary_is_checked_after_current_authority_state():
    source = inspect.getsource(
        memory_narrative_summary
        .get_memory_narrative_summary
    )

    load_position = source.index(
        "_load_active_memories"
    )
    hash_position = source.index(
        "_authoritative_source_hash"
    )
    persisted_position = source.index(
        "_load_latest_persisted_summary"
    )

    assert (
        load_position
        < hash_position
        < persisted_position
    )

    assert (
        "_latest_memory_changed_at"
        not in source
    )


def test_health_summary_reports_provenance_without_legacy_upgrade():
    rows = [
        _memory(
            memory_id="direct",
            content="Direct fact",
            source_priority="explicit_user_statement",
        ),
        _memory(
            memory_id="confirmed",
            content="Canonical confirmed fact",
            source_priority="system_inference",
            last_user_confirmed_at=(
                "2026-09-05T00:00:00+00:00"
            ),
        ),
        _memory(
            memory_id="legacy",
            content="Legacy weak fact",
            source_priority="system_inference",
            last_confirmed_at=(
                "2026-09-05T00:00:00+00:00"
            ),
        ),
        _memory(
            memory_id="hidden-direct",
            content="Archived direct fact",
            source_priority="explicit_user_statement",
            archived=True,
            status="archived",
        ),
    ]

    result = (
        memory_health_scheduler
        .build_user_memory_health_summaries(
            rows
        )
    )

    summary = result["user-1"]

    assert summary[
        "direct_user_memories"
    ] == 1

    assert summary[
        "canonically_confirmed_memories"
    ] == 1

    assert summary[
        "authoritative_memories"
    ] == 2

    assert summary[
        "unverified_memories"
    ] == 1


def test_health_loader_carries_canonical_provenance_and_is_read_only():
    source = inspect.getsource(
        memory_health_scheduler
        ._load_memory_rows
    )

    for field in (
        "source_priority",
        "confidence",
        "last_user_confirmed_at",
        "last_user_confirmation_source",
        "last_user_confirmation_evidence",
    ):
        assert field in source

    assert ".update(" not in source
    assert ".insert(" not in source
    assert ".delete(" not in source


def test_narrative_select_includes_canonical_confirmation():
    assert (
        "last_user_confirmed_at"
        in memory_narrative_summary
        ._MEMORY_SELECT
    )

    assert (
        "last_user_confirmation_source"
        in memory_narrative_summary
        ._MEMORY_SELECT
    )
