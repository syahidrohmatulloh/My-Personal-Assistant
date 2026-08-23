
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.memory_note_projection import project_memory_rows, summarize_note_projection
from app.services.supabase_client import get_supabase


DEFAULT_OUTPUT = Path("eval/m3_memory_note_projection_report.local.json")

MEMORY_SELECT_FIELDS = (
    "id,content,kind,category,status,source,source_conversation_id,evidence,"
    "structured_field,structured_value,superseded,superseded_by,archived,deleted_at,"
    "lifecycle_type,due_date,expires_at,calendar_candidate,calendar_event_status,"
    "calendar_event_title,calendar_event_date,calendar_event_start_at,calendar_event_end_at,"
    "calendar_event_location,created_at,updated_at,last_confirmed_at"
)


def fetch_memory_rows(max_rows: int = 20000) -> list[dict[str, Any]]:
    sb = get_supabase()
    result = (
        sb.table("memories")
        .select(MEMORY_SELECT_FIELDS)
        .order("created_at", desc=False)
        .range(0, max_rows - 1)
        .execute()
    )
    return list(result.data or [])


def build_projection_report(rows: list[dict[str, Any]], *, sample_size: int = 20) -> dict[str, Any]:
    notes = project_memory_rows(rows)
    summary = summarize_note_projection(notes)

    total = len(notes)
    source_backed = sum(1 for note in notes if (note.get("source") or {}).get("source_conversation_id"))
    evidence_backed = sum(1 for note in notes if (note.get("source") or {}).get("has_evidence"))
    with_entities = sum(1 for note in notes if note.get("entities"))
    timeline_notes = sum(1 for note in notes if note.get("timeline_date") or note.get("has_temporal_anchor"))
    retrievable = sum(1 for note in notes if (note.get("lifecycle") or {}).get("retrievable"))

    report = {
        "audit_version": "M3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "runtime_retrieval_change": False,
        "privacy_note": "No raw memory body, raw title, raw entity name, or source conversation ID is included.",
        "input_rows": len(rows),
        "projected_notes": total,
        "summary": summary,
        "coverage": {
            "retrievable_note_count": retrievable,
            "retrievable_note_rate": _rate(retrievable, total),
            "source_backed_note_count": source_backed,
            "source_backed_note_rate": _rate(source_backed, total),
            "evidence_backed_note_count": evidence_backed,
            "evidence_backed_note_rate": _rate(evidence_backed, total),
            "entity_note_count": with_entities,
            "entity_note_rate": _rate(with_entities, total),
            "timeline_note_count": timeline_notes,
            "timeline_note_rate": _rate(timeline_notes, total),
        },
        "obsidian_readiness": {
            "review_card_projection_ready": total > 0,
            "tag_index_projection_ready": bool(summary.get("top_tags")),
            "entity_index_projection_ready": with_entities > 0,
            "timeline_projection_ready": timeline_notes > 0,
            "evidence_projection_ready": source_backed > 0 or evidence_backed > 0,
            "backlink_projection_ready": False,
            "schema_migration_recommended_now": False,
            "runtime_retrieval_change_recommended_now": False,
        },
        "recommended_next_slice": {
            "name": "M4 read-only note index service",
            "objective": "Build pure in-memory indexes for tags, entities, timeline buckets, and candidate links without new tables.",
            "runtime_change": "No",
            "deploy_needed": "No",
        },
        "redacted_note_samples": [redact_note(note) for note in notes[:sample_size]],
    }
    return report


def redact_note(note: dict[str, Any]) -> dict[str, Any]:
    source = note.get("source") or {}
    lifecycle = note.get("lifecycle") or {}

    return {
        "id_hash": _hash(note.get("id")),
        "title_hash": _hash(note.get("title")),
        "body_hash": _hash(note.get("body")),
        "body_char_count": len(str(note.get("body") or "")),
        "body_word_count": len(str(note.get("body") or "").split()),
        "note_type": note.get("note_type"),
        "tags": list(note.get("tags") or []),
        "entity_count": len(note.get("entities") or []),
        "entity_types": sorted({str(entity.get("entity_type")) for entity in note.get("entities") or []}),
        "has_source_conversation_id": bool(source.get("source_conversation_id")),
        "has_evidence": bool(source.get("has_evidence")),
        "evidence_count": int(source.get("evidence_count") or 0),
        "status": lifecycle.get("status"),
        "retrievable": bool(lifecycle.get("retrievable")),
        "has_timeline_date": bool(note.get("timeline_date")),
        "has_temporal_anchor": bool(note.get("has_temporal_anchor")),
    }


def write_report(report: dict[str, Any], output_path: Path = DEFAULT_OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


def _hash(value: Any) -> str:
    return hashlib.blake2b(str(value or "").encode("utf-8"), digest_size=8).hexdigest()


def _rate(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(count / total, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a redacted local projection report for Obsidian-like memory notes.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-rows", type=int, default=20000)
    args = parser.parse_args()

    rows = fetch_memory_rows(max_rows=args.max_rows)
    report = build_projection_report(rows)
    output_path = Path(args.output)
    write_report(report, output_path)

    printable = {
        "audit_version": report["audit_version"],
        "input_rows": report["input_rows"],
        "projected_notes": report["projected_notes"],
        "coverage": report["coverage"],
        "obsidian_readiness": report["obsidian_readiness"],
        "recommended_next_slice": report["recommended_next_slice"],
    }
    print(json.dumps(printable, indent=2, default=str))
    print()
    print("[OK] wrote " + str(output_path))


if __name__ == "__main__":
    main()
