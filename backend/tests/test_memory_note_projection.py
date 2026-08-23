
from app.services.memory_note_projection import (
    has_temporal_anchor,
    infer_note_type,
    is_retrievable_memory,
    project_memory_row,
    project_memory_rows,
    summarize_note_projection,
)


def test_projects_preference_memory_into_note():
    row = {
        "id": "mem-1",
        "content": "User prefers concise replies",
        "kind": "preference",
        "category": "preferences",
        "source": "auto",
        "source_conversation_id": "conv-1",
        "evidence": ["I prefer concise replies"],
        "status": "active",
    }

    note = project_memory_row(row)

    assert note["id"] == "mem-1"
    assert note["note_type"] == "preference"
    assert note["title"] == "User prefers concise replies"
    assert "type:preference" in note["tags"]
    assert "category:preferences" in note["tags"]
    assert note["source"]["source_conversation_id"] == "conv-1"
    assert note["source"]["evidence_count"] == 1
    assert note["lifecycle"]["retrievable"] is True


def test_projects_structured_identity_entity():
    row = {
        "id": "mem-2",
        "content": "User child name is Zahra",
        "kind": "fact",
        "category": "relationships",
        "structured_field": "child_name",
        "structured_value": "Zahra",
        "status": "active",
    }

    note = project_memory_row(row)

    assert note["note_type"] == "relationship"
    assert note["title"] == "Child Name: Zahra"
    assert note["entities"] == [
        {
            "name": "Zahra",
            "entity_type": "person",
            "source": "structured_field:child_name",
            "confidence": 0.9,
        }
    ]
    assert "field:child_name" in note["tags"]
    assert "family" in note["tags"]


def test_projects_calendar_memory_into_event_note():
    row = {
        "id": "mem-3",
        "content": "Meeting with product team tomorrow morning",
        "kind": "plan",
        "category": "goals",
        "structured_field": "scheduled_event",
        "structured_value": "Meeting with product team",
        "lifecycle_type": "time_bound",
        "due_date": "2026-08-24",
        "calendar_event_status": "confirmed_local",
        "calendar_event_title": "Meeting with product team",
        "status": "active",
    }

    note = project_memory_row(row)

    assert infer_note_type(row) == "event"
    assert note["note_type"] == "event"
    assert note["title"] == "Meeting with product team"
    assert note["timeline_date"] == "2026-08-24"
    assert note["has_temporal_anchor"] is True
    assert "type:event" in note["tags"]
    assert "calendar" in note["tags"]
    assert "timeline" in note["tags"]
    assert note["entities"][0]["entity_type"] == "event"


def test_hidden_lifecycle_is_not_retrievable():
    row = {
        "id": "mem-4",
        "content": "Old preference",
        "kind": "preference",
        "status": "archived",
        "archived": True,
        "superseded": False,
    }

    note = project_memory_row(row)

    assert is_retrievable_memory(row) is False
    assert note["lifecycle"]["retrievable"] is False


def test_superseded_memory_is_not_retrievable():
    row = {
        "id": "mem-5",
        "content": "Old birthday",
        "kind": "fact",
        "category": "identity",
        "status": "active",
        "superseded": True,
        "superseded_by": "mem-6",
    }

    note = project_memory_row(row)

    assert note["note_type"] == "identity"
    assert note["lifecycle"]["retrievable"] is False
    assert note["lifecycle"]["superseded_by"] == "mem-6"


def test_projection_summary_groups_notes():
    rows = [
        {"id": "1", "content": "User prefers coffee", "kind": "preference", "category": "preferences", "status": "active"},
        {"id": "2", "content": "Meeting tomorrow", "kind": "plan", "structured_field": "scheduled_event", "due_date": "2026-08-24", "status": "active"},
        {"id": "3", "content": "Archived fact", "kind": "fact", "status": "archived", "archived": True},
    ]

    notes = project_memory_rows(rows)
    summary = summarize_note_projection(notes)

    assert summary["total_notes"] == 3
    assert summary["by_type"]["preference"] == 1
    assert summary["by_type"]["event"] == 1
    assert summary["retrievable_note_count"] == 2
    assert summary["timeline_note_count"] >= 1


def test_temporal_anchor_detects_dates_and_terms():
    assert has_temporal_anchor({"content": "Call tomorrow morning"}) is True
    assert has_temporal_anchor({"content": "Birthday is 2026-08-24"}) is True
    assert has_temporal_anchor({"content": "Likes coffee"}) is False
