
from app.services.memory_graph_view_model import (
    build_memory_graph_view_model,
    build_note_card,
)
from app.services.memory_note_projection import project_memory_rows


def test_builds_graph_view_model_sections():
    notes = project_memory_rows(
        [
            {
                "id": "mem-1",
                "content": "User child name is Zahra",
                "kind": "fact",
                "category": "relationships",
                "structured_field": "child_name",
                "structured_value": "Zahra",
                "source_conversation_id": "conv-1",
                "status": "active",
            },
            {
                "id": "mem-2",
                "content": "Zahra school planning tomorrow morning",
                "kind": "plan",
                "category": "goals",
                "structured_field": "scheduled_event",
                "structured_value": "Zahra",
                "due_date": "2026-08-24",
                "calendar_event_title": "Zahra school planning",
                "evidence": ["User mentioned school planning"],
                "status": "active",
            },
        ]
    )

    view = build_memory_graph_view_model(notes)

    assert view["read_only"] is True
    assert view["runtime_retrieval_change"] is False
    assert view["schema_migration"] is False
    assert view["summary"]["input_note_count"] == 2
    assert view["summary"]["visible_note_count"] == 2
    assert view["summary"]["tag_section_count"] > 0
    assert view["summary"]["entity_section_count"] > 0
    assert view["summary"]["timeline_section_count"] >= 1
    assert "notes" in view["sections"]
    assert "tags" in view["sections"]
    assert "entities" in view["sections"]
    assert "timeline" in view["sections"]
    assert "candidate_backlinks" in view["sections"]


def test_note_cards_include_preview_source_lifecycle_and_related_notes():
    notes = project_memory_rows(
        [
            {
                "id": "mem-1",
                "content": "User child name is Zahra",
                "kind": "fact",
                "category": "relationships",
                "structured_field": "child_name",
                "structured_value": "Zahra",
                "source_conversation_id": "conv-1",
                "status": "active",
            },
            {
                "id": "mem-2",
                "content": "Zahra school planning tomorrow morning",
                "kind": "fact",
                "category": "relationships",
                "structured_field": "child_name",
                "structured_value": "Zahra",
                "status": "active",
            },
        ]
    )

    view = build_memory_graph_view_model(notes)
    cards = {card["id"]: card for card in view["sections"]["notes"]}

    assert cards["mem-1"]["title"] == "Child Name: Zahra"
    assert cards["mem-1"]["source"]["has_source_conversation_id"] is True
    assert cards["mem-1"]["lifecycle"]["retrievable"] is True
    assert cards["mem-1"]["related_note_ids"] == ["mem-2"]
    assert cards["mem-2"]["related_note_ids"] == ["mem-1"]


def test_view_model_excludes_non_retrievable_by_default():
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

    view = build_memory_graph_view_model(notes)

    assert view["summary"]["input_note_count"] == 2
    assert view["summary"]["visible_note_count"] == 1
    assert [card["id"] for card in view["sections"]["notes"]] == ["mem-1"]


def test_view_model_can_include_non_retrievable_when_requested():
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

    view = build_memory_graph_view_model(notes, retrievable_only=False)

    assert view["summary"]["visible_note_count"] == 1
    assert view["sections"]["notes"][0]["lifecycle"]["retrievable"] is False


def test_build_note_card_truncates_preview():
    card = build_note_card(
        {
            "id": "mem-1",
            "title": "Title",
            "body": "one two three four five",
            "note_type": "fact",
            "tags": [],
            "source": {},
            "lifecycle": {"retrievable": True},
        },
        preview_chars=9,
    )

    assert card["body_preview"] == "one two…"
