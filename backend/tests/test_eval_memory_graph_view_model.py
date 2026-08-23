
from tools.eval_memory_graph_view_model import (
    build_graph_view_report,
    redact_backlink_section,
    redact_entity_section,
    redact_note_card,
)


def test_build_graph_view_report_is_redacted_and_ui_ready():
    rows = [
        {
            "id": "mem-1",
            "content": "User child name is Zahra",
            "kind": "fact",
            "category": "relationships",
            "structured_field": "child_name",
            "structured_value": "Zahra",
            "source_conversation_id": "conv-secret",
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
            "evidence": ["User mentioned Zahra school planning"],
            "status": "active",
        },
    ]

    report = build_graph_view_report(rows, sample_size=10)

    assert report["read_only"] is True
    assert report["runtime_retrieval_change"] is False
    assert report["schema_migration"] is False
    assert report["input_rows"] == 2
    assert report["projected_notes"] == 2
    assert report["section_counts"]["note_cards"] == 2
    assert report["section_counts"]["tag_sections"] > 0
    assert report["section_counts"]["entity_sections"] > 0
    assert report["section_counts"]["timeline_sections"] >= 1
    assert report["ui_readiness"]["note_review_cards_ready"] is True
    assert report["ui_readiness"]["tag_filter_ready"] is True
    assert report["ui_readiness"]["entity_filter_ready"] is True
    assert report["ui_readiness"]["timeline_view_ready"] is True
    assert report["ui_readiness"]["runtime_retrieval_change_recommended_now"] is False

    rendered = str(report)
    assert "Zahra" not in rendered
    assert "conv-secret" not in rendered
    assert "User child name is Zahra" not in rendered
    assert "Zahra school planning" not in rendered


def test_redact_note_card_omits_raw_id_title_body_and_related_ids():
    card = {
        "id": "mem-1",
        "title": "Secret title",
        "body_preview": "Secret body",
        "note_type": "fact",
        "tags": ["family"],
        "entity_count": 1,
        "timeline_date": "2026-08-24",
        "has_temporal_anchor": True,
        "source": {
            "has_source_conversation_id": True,
            "has_evidence": True,
            "evidence_count": 2,
        },
        "lifecycle": {
            "status": "active",
            "retrievable": True,
        },
        "related_note_ids": ["mem-2"],
    }

    redacted = redact_note_card(card)
    rendered = str(redacted)

    assert "mem-1" not in rendered
    assert "mem-2" not in rendered
    assert "Secret title" not in rendered
    assert "Secret body" not in rendered
    assert redacted["note_type"] == "fact"
    assert redacted["entity_count"] == 1
    assert redacted["related_note_count"] == 1


def test_redact_entity_section_omits_raw_entity_and_note_ids():
    section = {
        "entity_key": "person:zahra",
        "entity_type": "person",
        "entity_name": "Zahra",
        "count": 2,
        "note_ids": ["mem-1", "mem-2"],
    }

    redacted = redact_entity_section(section)
    rendered = str(redacted)

    assert "zahra" not in rendered
    assert "Zahra" not in rendered
    assert "mem-1" not in rendered
    assert "mem-2" not in rendered
    assert redacted["entity_type"] == "person"
    assert redacted["count"] == 2


def test_redact_backlink_section_omits_raw_ids_and_reason_values():
    section = {
        "source_note_id": "mem-1",
        "target_note_id": "mem-2",
        "score": 3.0,
        "reasons": ["entity:person:zahra", "tag:family"],
    }

    redacted = redact_backlink_section(section)
    rendered = str(redacted)

    assert "mem-1" not in rendered
    assert "mem-2" not in rendered
    assert "zahra" not in rendered
    assert "family" not in rendered
    assert redacted["reason_types"] == ["entity", "tag"]
