
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.memory_graph_view_model import build_memory_graph_view_model
from app.services.memory_note_projection import project_memory_rows
from tools.eval_memory_note_projection import fetch_memory_rows


DEFAULT_OUTPUT = Path("eval/m7_memory_graph_view_report.local.json")


def build_graph_view_report(
    rows: list[dict[str, Any]],
    *,
    sample_size: int = 20,
    max_links_per_note: int = 5,
) -> dict[str, Any]:
    notes = project_memory_rows(rows)
    view = build_memory_graph_view_model(
        notes,
        retrievable_only=True,
        max_links_per_note=max_links_per_note,
    )

    sections = view.get("sections") or {}
    note_cards = list(sections.get("notes") or [])
    tag_sections = list(sections.get("tags") or [])
    entity_sections = list(sections.get("entities") or [])
    timeline_sections = list(sections.get("timeline") or [])
    backlink_sections = list(sections.get("candidate_backlinks") or [])

    report = {
        "audit_version": "M7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "runtime_retrieval_change": False,
        "schema_migration": False,
        "privacy_note": "No raw note title, body preview, entity name, source conversation ID, or note ID is included.",
        "input_rows": len(rows),
        "projected_notes": len(notes),
        "view_summary": view.get("summary") or {},
        "section_counts": {
            "note_cards": len(note_cards),
            "type_sections": len(sections.get("types") or []),
            "tag_sections": len(tag_sections),
            "entity_sections": len(entity_sections),
            "timeline_sections": len(timeline_sections),
            "candidate_backlink_sections": len(backlink_sections),
        },
        "coverage": {
            "cards_with_tags_rate": _rate(sum(1 for card in note_cards if card.get("tags")), len(note_cards)),
            "cards_with_entities_rate": _rate(sum(1 for card in note_cards if card.get("entity_count", 0) > 0), len(note_cards)),
            "cards_with_timeline_rate": _rate(sum(1 for card in note_cards if card.get("timeline_date") or card.get("has_temporal_anchor")), len(note_cards)),
            "cards_with_evidence_rate": _rate(sum(1 for card in note_cards if (card.get("source") or {}).get("has_evidence")), len(note_cards)),
            "cards_with_source_conversation_rate": _rate(sum(1 for card in note_cards if (card.get("source") or {}).get("has_source_conversation_id")), len(note_cards)),
            "cards_with_related_notes_rate": _rate(sum(1 for card in note_cards if card.get("related_note_ids")), len(note_cards)),
        },
        "ui_readiness": {
            "note_review_cards_ready": len(note_cards) > 0,
            "tag_filter_ready": len(tag_sections) > 0,
            "entity_filter_ready": len(entity_sections) > 0,
            "timeline_view_ready": len(timeline_sections) > 0,
            "candidate_backlinks_ready": len(backlink_sections) > 0,
            "safe_to_expose_without_raw_source_ids": True,
            "runtime_retrieval_change_recommended_now": False,
            "schema_migration_recommended_now": False,
        },
        "recommended_next_slice": {
            "name": "M8 implementation decision",
            "objective": "Choose between docs-only closeout, PIN-gated read-only backend endpoint, or frontend review UI prototype.",
            "recommended_path": "Docs-only closeout first, then PIN-gated read-only endpoint if we want to expose this in app.",
            "runtime_change": "Not yet",
            "deploy_needed": "No for docs-only; yes only if endpoint/UI is added later.",
        },
        "redacted_samples": {
            "note_cards": [redact_note_card(card) for card in note_cards[:sample_size]],
            "tags": [redact_tag_section(item) for item in tag_sections[:sample_size]],
            "entities": [redact_entity_section(item) for item in entity_sections[:sample_size]],
            "timeline": [redact_timeline_section(item) for item in timeline_sections[:sample_size]],
            "candidate_backlinks": [redact_backlink_section(item) for item in backlink_sections[:sample_size]],
        },
    }
    return report


def redact_note_card(card: dict[str, Any]) -> dict[str, Any]:
    source = card.get("source") or {}
    lifecycle = card.get("lifecycle") or {}
    return {
        "id_hash": _hash(card.get("id")),
        "title_hash": _hash(card.get("title")),
        "body_preview_hash": _hash(card.get("body_preview")),
        "body_preview_char_count": len(str(card.get("body_preview") or "")),
        "note_type": card.get("note_type"),
        "tags": list(card.get("tags") or []),
        "entity_count": int(card.get("entity_count") or 0),
        "timeline_date_hash": _hash(card.get("timeline_date")) if card.get("timeline_date") else None,
        "has_temporal_anchor": bool(card.get("has_temporal_anchor")),
        "has_source_conversation_id": bool(source.get("has_source_conversation_id")),
        "has_evidence": bool(source.get("has_evidence")),
        "evidence_count": int(source.get("evidence_count") or 0),
        "status": lifecycle.get("status"),
        "retrievable": bool(lifecycle.get("retrievable")),
        "related_note_count": len(card.get("related_note_ids") or []),
        "related_note_id_hashes": [_hash(value) for value in list(card.get("related_note_ids") or [])[:10]],
    }


def redact_tag_section(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag": section.get("tag"),
        "count": int(section.get("count") or 0),
        "note_id_hashes": [_hash(value) for value in list(section.get("note_ids") or [])[:10]],
    }


def redact_entity_section(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_key_hash": _hash(section.get("entity_key")),
        "entity_type": section.get("entity_type"),
        "entity_name_hash": _hash(section.get("entity_name")),
        "count": int(section.get("count") or 0),
        "note_id_hashes": [_hash(value) for value in list(section.get("note_ids") or [])[:10]],
    }


def redact_timeline_section(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "date_hash": _hash(section.get("date")),
        "count": int(section.get("count") or 0),
        "note_id_hashes": [_hash(value) for value in list(section.get("note_ids") or [])[:10]],
    }


def redact_backlink_section(section: dict[str, Any]) -> dict[str, Any]:
    reasons = list(section.get("reasons") or [])
    return {
        "source_note_id_hash": _hash(section.get("source_note_id")),
        "target_note_id_hash": _hash(section.get("target_note_id")),
        "score": section.get("score"),
        "reason_count": len(reasons),
        "reason_types": sorted({_reason_type(reason) for reason in reasons}),
        "reason_hashes": [_hash(reason) for reason in reasons],
    }


def write_report(report: dict[str, Any], output_path: Path = DEFAULT_OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


def _reason_type(reason: Any) -> str:
    text = str(reason or "")
    if ":" not in text:
        return "unknown"
    return text.split(":", 1)[0].strip() or "unknown"


def _hash(value: Any) -> str:
    return hashlib.blake2b(str(value or "").encode("utf-8"), digest_size=8).hexdigest()


def _rate(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(count / total, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a redacted local report for memory graph view model.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-rows", type=int, default=20000)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--max-links-per-note", type=int, default=5)
    args = parser.parse_args()

    rows = fetch_memory_rows(max_rows=args.max_rows)
    report = build_graph_view_report(
        rows,
        sample_size=args.sample_size,
        max_links_per_note=args.max_links_per_note,
    )
    output_path = Path(args.output)
    write_report(report, output_path)

    printable = {
        "audit_version": report["audit_version"],
        "input_rows": report["input_rows"],
        "projected_notes": report["projected_notes"],
        "view_summary": report["view_summary"],
        "section_counts": report["section_counts"],
        "coverage": report["coverage"],
        "ui_readiness": report["ui_readiness"],
        "recommended_next_slice": report["recommended_next_slice"],
    }
    print(json.dumps(printable, indent=2, default=str))
    print()
    print("[OK] wrote " + str(output_path))


if __name__ == "__main__":
    main()
