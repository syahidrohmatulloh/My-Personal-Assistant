
from tools.eval_memory_note_index import (
    build_note_index_report,
    redact_candidate_link,
    redact_entity_bucket,
)


def test_build_note_index_report_is_redacted_and_counts_indexes():
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
            "content": "Zahra school planning tomorrow",
            "kind": "fact",
            "category": "relationships",
            "structured_field": "child_name",
            "structured_value": "Zahra",
            "due_date": "2026-08-24",
            "calendar_event_title": "Zahra school planning",
            "evidence": ["User mentioned Zahra school"],
            "status": "active",
        },
        {
            "id": "mem-3",
            "content": "Archived preference",
            "kind": "preference",
            "status": "archived",
            "archived": True,
        },
    ]

    report = build_note_index_report(rows, sample_size=10)

    assert report["read_only"] is True
    assert report["runtime_retrieval_change"] is False
    assert report["schema_migration"] is False
    assert report["input_rows"] == 3
    assert report["projected_notes"] == 3
    assert report["indexed_note_count"] == 2
    assert report["omitted_non_retrievable_note_count"] == 1
    assert report["index_summary"]["tag_count"] > 0
    assert report["index_summary"]["entity_count"] > 0
    assert report["index_summary"]["timeline_bucket_count"] >= 1
    assert report["index_summary"]["candidate_link_count"] >= 1
    assert report["coverage"]["entity_indexed_note_count"] == 2
    assert report["coverage"]["candidate_linked_note_count"] == 2
    assert report["obsidian_readiness"]["candidate_backlink_projection_ready"] is True
    assert report["obsidian_readiness"]["runtime_retrieval_change_recommended_now"] is False
    assert report["obsidian_readiness"]["schema_migration_recommended_now"] is False

    rendered = str(report)
    assert "Zahra" not in rendered
    assert "conv-secret" not in rendered
    assert "User child name is Zahra" not in rendered
    assert "Zahra school planning" not in rendered


def test_redact_candidate_link_omits_raw_ids_and_reason_values():
    link = {
        "source_note_id": "mem-1",
        "target_note_id": "mem-2",
        "score": 3.0,
        "reasons": ["entity:person:zahra", "tag:family"],
    }

    redacted = redact_candidate_link(link)
    rendered = str(redacted)

    assert "mem-1" not in rendered
    assert "mem-2" not in rendered
    assert "zahra" not in rendered
    assert "family" not in rendered
    assert redacted["reason_types"] == ["entity", "tag"]
    assert len(redacted["reason_hashes"]) == 2


def test_redact_entity_bucket_omits_raw_entity_key_and_note_ids():
    bucket = {
        "entity_type": "person",
        "entity_name": "Zahra",
        "note_ids": ["mem-1", "mem-2"],
    }

    redacted = redact_entity_bucket("person:zahra", bucket)
    rendered = str(redacted)

    assert "zahra" not in rendered
    assert "Zahra" not in rendered
    assert "mem-1" not in rendered
    assert "mem-2" not in rendered
    assert redacted["entity_type"] == "person"
    assert redacted["note_count"] == 2
    assert len(redacted["note_id_hashes"]) == 2
