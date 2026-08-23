
from tools.eval_memory_note_projection import build_projection_report, redact_note


def test_build_projection_report_is_redacted_and_counts_projection():
    rows = [
        {
            "id": "mem-1",
            "content": "User prefers sushi for dinner",
            "kind": "preference",
            "category": "preferences",
            "source": "auto",
            "source_conversation_id": "conv-secret",
            "evidence": ["User said sushi"],
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

    report = build_projection_report(rows, sample_size=2)

    assert report["read_only"] is True
    assert report["runtime_retrieval_change"] is False
    assert report["input_rows"] == 2
    assert report["projected_notes"] == 2
    assert report["coverage"]["source_backed_note_count"] == 1
    assert report["coverage"]["evidence_backed_note_count"] == 1
    assert report["coverage"]["timeline_note_count"] >= 1
    assert report["obsidian_readiness"]["review_card_projection_ready"] is True
    assert report["obsidian_readiness"]["runtime_retrieval_change_recommended_now"] is False

    rendered = str(report)
    assert "User prefers sushi for dinner" not in rendered
    assert "Meeting with Zahra" not in rendered
    assert "conv-secret" not in rendered


def test_redact_note_omits_raw_title_body_entity_names_and_source_id():
    note = {
        "id": "mem-1",
        "title": "Secret title",
        "body": "Secret body",
        "note_type": "relationship",
        "tags": ["family"],
        "entities": [
            {
                "name": "Zahra",
                "entity_type": "person",
                "source": "structured_field:child_name",
                "confidence": 0.9,
            }
        ],
        "source": {
            "source": "auto",
            "source_conversation_id": "conv-secret",
            "has_evidence": True,
            "evidence_count": 2,
        },
        "lifecycle": {
            "status": "active",
            "retrievable": True,
        },
        "timeline_date": "2026-08-24",
        "has_temporal_anchor": True,
    }

    redacted = redact_note(note)
    rendered = str(redacted)

    assert "Secret title" not in rendered
    assert "Secret body" not in rendered
    assert "Zahra" not in rendered
    assert "conv-secret" not in rendered
    assert redacted["entity_count"] == 1
    assert redacted["entity_types"] == ["person"]
    assert redacted["has_source_conversation_id"] is True
    assert redacted["has_evidence"] is True
