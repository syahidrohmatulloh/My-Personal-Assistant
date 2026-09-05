from __future__ import annotations

import inspect

from app.routers import memories
from app.services import habit_learning
from app.services import memory
from app.services import memory_supersession
from app.services import mood_memory_feedback
from app.services import relationship_memory


def test_hidden_state_helper_covers_all_hidden_lifecycle_states():
    hidden_rows = [
        {"archived": True},
        {"superseded": True},
        {"deleted_at": "2026-09-05T00:00:00Z"},
        {"status": "archived"},
        {"status": "superseded"},
        {"status": "deleted"},
    ]

    for row in hidden_rows:
        assert memory_supersession._row_is_hidden(row) is True

    assert (
        memory_supersession._row_is_hidden(
            {
                "archived": False,
                "superseded": False,
                "status": "active",
                "deleted_at": None,
            }
        )
        is False
    )


def test_apply_supersession_phase_never_updates_existing_rows():
    source = inspect.getsource(
        memory_supersession.apply_memory_supersession
    )

    assert ".update(" not in source
    assert "_hidden_equivalent_exists" in source


def test_finalize_supersession_is_post_insert_mutation_phase():
    source = inspect.getsource(
        memory_supersession.finalize_memory_supersession
    )

    assert "_finalize_existing_for_row" in source

    finalize_source = inspect.getsource(
        memory_supersession._finalize_existing_for_row
    )

    assert '"superseded": True' in finalize_source
    assert '"superseded_by": new_id' in finalize_source
    assert '"status": "superseded"' in finalize_source
    assert '"archived": True' not in finalize_source


def test_legacy_memory_insert_occurs_before_supersession_finalize():
    source = inspect.getsource(
        memory.extract_and_save
    )

    insert_position = source.index(
        '.insert(rows)'
    )
    finalize_position = source.index(
        'finalize_memory_supersession('
    )

    assert insert_position < finalize_position


def test_machine_supersession_cannot_replace_authoritative_old_truth():
    assert (
        memory_supersession._row_is_authoritative(
            {
                "source_priority": "explicit_user_statement",
            }
        )
        is True
    )

    assert (
        memory_supersession._row_is_authoritative(
            {
                "source_priority": "system_inference",
                "last_user_confirmed_at": (
                    "2026-09-05T00:00:00Z"
                ),
            }
        )
        is True
    )

    assert (
        memory_supersession._row_is_authoritative(
            {
                "source_priority": "system_inference",
                "last_confirmed_at": (
                    "2026-09-05T00:00:00Z"
                ),
            }
        )
        is False
    )


def test_relationship_writer_has_hidden_resurrection_guard():
    source = inspect.getsource(
        relationship_memory._upsert_candidate
    )

    assert "_memory_row_hidden" in source
    assert "hidden_existing_preserved" in source
    assert "confirmed_existing" not in source


def test_mood_writer_has_hidden_resurrection_guard():
    source = inspect.getsource(
        mood_memory_feedback._upsert_candidate
    )

    assert "_memory_row_hidden" in source
    assert "hidden_existing_preserved" in source
    assert "confirmed_existing" not in source


def test_habit_writer_has_hidden_resurrection_guard():
    source = inspect.getsource(
        habit_learning.persist_habit_candidate
    )

    assert "hidden_existing_preserved" in source
    assert "hidden_rows" in source


def test_habit_user_correction_is_supersession_not_archive():
    source = inspect.getsource(
        habit_learning.supersede_inferred_habit
    )

    assert '"superseded": True' in source
    assert '"status": "superseded"' in source
    assert '"archived": True' not in source
    assert '"archived_by"' not in source


def test_automatic_writer_payloads_never_claim_user_confirmation():
    relationship_source = inspect.getsource(
        relationship_memory.RelationshipMemoryCandidate.as_memory_payload
    )
    mood_source = inspect.getsource(
        mood_memory_feedback.BehavioralMemoryCandidate.as_memory_payload
    )
    habit_source = inspect.getsource(
        habit_learning.persist_habit_candidate
    )

    for source in (
        relationship_source,
        mood_source,
        habit_source,
    ):
        assert '"last_user_confirmed_at": None' in source


def test_legacy_mutation_endpoints_are_retired():
    create_source = inspect.getsource(
        memories.create_memory
    )
    delete_source = inspect.getsource(
        memories.delete_memory
    )
    clear_source = inspect.getsource(
        memories.clear_all_memories
    )

    for source in (
        create_source,
        delete_source,
        clear_source,
    ):
        assert "_legacy_mutation_retired()" in source

    assert ".insert(" not in create_source
    assert ".delete()" not in delete_source
    assert ".delete()" not in clear_source


def test_legacy_retirement_uses_http_410():
    source = inspect.getsource(
        memories._legacy_mutation_retired
    )

    assert "HTTP_410_GONE" in source
