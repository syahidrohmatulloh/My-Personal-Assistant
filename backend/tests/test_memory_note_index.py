
from app.services.memory_note_index import (
    build_candidate_links,
    build_note_index,
    candidate_link_score,
    entity_key,
)
from app.services.memory_note_projection import project_memory_row, project_memory_rows


def test_builds_tag_entity_timeline_and_type_indexes():
    notes = project_memory_rows(
        [
            {
                "id": "mem-1",
                "content": "User child name is Zahra",
                "kind": "fact",
                "category": "relationships",
                "structured_field": "child_name",
                "structured_value": "Zahra",
                "status": "active",
            },
            {
                "id": "mem-2",
                "content": "Meeting with Zahra tomorrow morning",
                "kind": "plan",
                "structured_field": "scheduled_event",
                "structured_value": "Meeting with Zahra",
                "due_date": "2026-08-24",
                "calendar_event_title": "Meeting with Zahra",
                "status": "active",
            },
        ]
    )

    index = build_note_index(notes)

    assert index["indexed_note_count"] == 2
    assert "relationship" in index["type_index"]
    assert "event" in index["type_index"]
    assert "family" in index["tag_index"]
    assert "person:zahra" in index["entity_index"]
    assert "event:meeting with zahra" in index["entity_index"]
    assert index["timeline_index"]["2026-08-24"] == ["mem-2"]


def test_excludes_non_retrievable_notes_by_default():
    notes = project_memory_rows(
        [
            {
                "id": "mem-1",
                "content": "Active memory",
                "kind": "fact",
                "status": "active",
            },
            {
                "id": "mem-2",
                "content": "Archived memory",
                "kind": "fact",
                "status": "archived",
                "archived": True,
            },
        ]
    )

    index = build_note_index(notes)

    assert index["total_input_notes"] == 2
    assert index["indexed_note_count"] == 1
    assert "mem-1" in index["note_refs"]
    assert "mem-2" not in index["note_refs"]


def test_can_include_non_retrievable_notes_when_requested():
    notes = project_memory_rows(
        [
            {
                "id": "mem-1",
                "content": "Archived memory",
                "kind": "fact",
                "status": "archived",
                "archived": True,
            },
        ]
    )

    index = build_note_index(notes, retrievable_only=False)

    assert index["indexed_note_count"] == 1
    assert index["note_refs"]["mem-1"]["retrievable"] is False


def test_candidate_links_from_shared_entity():
    left = project_memory_row(
        {
            "id": "mem-1",
            "content": "User child name is Zahra",
            "kind": "fact",
            "category": "relationships",
            "structured_field": "child_name",
            "structured_value": "Zahra",
            "status": "active",
        }
    )
    right = project_memory_row(
        {
            "id": "mem-2",
            "content": "Zahra school planning",
            "kind": "fact",
            "category": "relationships",
            "structured_field": "child_name",
            "structured_value": "Zahra",
            "status": "active",
        }
    )

    score, reasons = candidate_link_score(left, right)
    links = build_candidate_links([left, right])

    assert score >= 3.0
    assert "entity:person:zahra" in reasons
    assert links[0].source_note_id == "mem-1"
    assert links[0].target_note_id == "mem-2"


def test_candidate_links_do_not_link_on_type_only():
    notes = project_memory_rows(
        [
            {"id": "mem-1", "content": "Likes coffee", "kind": "fact", "status": "active"},
            {"id": "mem-2", "content": "Lives in Jakarta", "kind": "fact", "status": "active"},
        ]
    )

    links = build_candidate_links(notes)

    assert links == []


def test_candidate_links_from_timeline_plus_shared_tag():
    left = project_memory_row(
        {
            "id": "mem-1",
            "content": "Project meeting tomorrow",
            "kind": "plan",
            "category": "goals",
            "structured_field": "scheduled_event",
            "due_date": "2026-08-24",
            "status": "active",
        }
    )
    right = project_memory_row(
        {
            "id": "mem-2",
            "content": "Project review tomorrow",
            "kind": "plan",
            "category": "goals",
            "structured_field": "scheduled_event",
            "due_date": "2026-08-24",
            "status": "active",
        }
    )

    score, reasons = candidate_link_score(left, right)

    assert score >= 2.0
    assert "timeline:2026-08-24" in reasons
    assert "tag:goal" in reasons


def test_entity_key_normalizes_name_and_type():
    entity = {
        "name": "  Zahra   Aliya  ",
        "entity_type": " Person ",
    }

    assert entity_key(entity) == "person:zahra aliya"
