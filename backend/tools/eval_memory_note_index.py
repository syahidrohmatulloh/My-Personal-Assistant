
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.memory_note_index import build_note_index
from app.services.memory_note_projection import project_memory_rows
from tools.eval_memory_note_projection import fetch_memory_rows


DEFAULT_OUTPUT = Path("eval/m5_memory_note_index_report.local.json")


def build_note_index_report(
    rows: list[dict[str, Any]],
    *,
    sample_size: int = 20,
    max_links_per_note: int = 5,
) -> dict[str, Any]:
    notes = project_memory_rows(rows)
    index = build_note_index(
        notes,
        retrievable_only=True,
        max_links_per_note=max_links_per_note,
    )

    indexed_note_ids = set(index.get("note_refs") or {})
    tag_index = index.get("tag_index") or {}
    entity_index = index.get("entity_index") or {}
    timeline_index = index.get("timeline_index") or {}
    type_index = index.get("type_index") or {}
    links = index.get("candidate_links") or []

    tag_note_ids = _note_ids_from_index(tag_index)
    entity_note_ids = _note_ids_from_entity_index(entity_index)
    timeline_note_ids = _note_ids_from_index(timeline_index)
    linked_note_ids = _note_ids_from_links(links)

    report = {
        "audit_version": "M5",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "runtime_retrieval_change": False,
        "schema_migration": False,
        "privacy_note": "No raw memory body, raw title, raw entity name, raw source conversation ID, or raw note ID is included.",
        "input_rows": len(rows),
        "projected_notes": len(notes),
        "indexed_note_count": len(indexed_note_ids),
        "omitted_non_retrievable_note_count": len(notes) - len(indexed_note_ids),
        "index_summary": {
            "type_count": len(type_index),
            "tag_count": len(tag_index),
            "entity_count": len(entity_index),
            "timeline_bucket_count": len(timeline_index),
            "candidate_link_count": len(links),
        },
        "coverage": {
            "tag_indexed_note_count": len(tag_note_ids),
            "tag_indexed_note_rate": _rate(len(tag_note_ids), len(indexed_note_ids)),
            "entity_indexed_note_count": len(entity_note_ids),
            "entity_indexed_note_rate": _rate(len(entity_note_ids), len(indexed_note_ids)),
            "timeline_indexed_note_count": len(timeline_note_ids),
            "timeline_indexed_note_rate": _rate(len(timeline_note_ids), len(indexed_note_ids)),
            "candidate_linked_note_count": len(linked_note_ids),
            "candidate_linked_note_rate": _rate(len(linked_note_ids), len(indexed_note_ids)),
            "avg_candidate_links_per_indexed_note": _rate(len(links), len(indexed_note_ids)),
        },
        "redacted_indexes": {
            "type_index_counts": _index_counts(type_index),
            "top_tag_index_counts": _top_counts(tag_index, limit=30),
            "entity_type_counts": _entity_type_counts(entity_index),
            "timeline_bucket_size_summary": _timeline_bucket_summary(timeline_index),
            "candidate_link_reason_type_counts": _candidate_reason_type_counts(links),
        },
        "obsidian_readiness": {
            "tag_index_ready": len(tag_index) > 0,
            "entity_index_ready": len(entity_index) > 0,
            "timeline_index_ready": len(timeline_index) > 0,
            "candidate_backlink_projection_ready": len(links) > 0,
            "review_ui_can_use_projection_without_schema": len(indexed_note_ids) > 0,
            "runtime_retrieval_change_recommended_now": False,
            "schema_migration_recommended_now": False,
        },
        "recommended_next_slice": {
            "name": "M6 read-only memory graph view model",
            "objective": "Create a pure view-model that turns projected notes and indexes into UI-ready sections: notes, tags, entities, timeline, and candidate backlinks.",
            "runtime_change": "No",
            "deploy_needed": "No",
        },
        "redacted_candidate_link_samples": [
            redact_candidate_link(link) for link in links[:sample_size]
        ],
        "redacted_entity_index_samples": [
            redact_entity_bucket(key, bucket)
            for key, bucket in list(sorted(entity_index.items()))[:sample_size]
        ],
    }
    return report


def redact_candidate_link(link: dict[str, Any]) -> dict[str, Any]:
    reasons = list(link.get("reasons") or [])
    return {
        "source_note_id_hash": _hash(link.get("source_note_id")),
        "target_note_id_hash": _hash(link.get("target_note_id")),
        "score": link.get("score"),
        "reason_count": len(reasons),
        "reason_types": sorted({_reason_type(reason) for reason in reasons}),
        "reason_hashes": [_hash(reason) for reason in reasons],
    }


def redact_entity_bucket(key: str, bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_key_hash": _hash(key),
        "entity_type": str(bucket.get("entity_type") or "concept"),
        "note_count": len(bucket.get("note_ids") or []),
        "note_id_hashes": [_hash(note_id) for note_id in list(bucket.get("note_ids") or [])[:10]],
    }


def write_report(report: dict[str, Any], output_path: Path = DEFAULT_OUTPUT) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


def _note_ids_from_index(index: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    for ids in index.values():
        out.update(str(note_id) for note_id in ids)
    return out


def _note_ids_from_entity_index(index: dict[str, dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for bucket in index.values():
        out.update(str(note_id) for note_id in bucket.get("note_ids") or [])
    return out


def _note_ids_from_links(links: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for link in links:
        if link.get("source_note_id"):
            out.add(str(link["source_note_id"]))
        if link.get("target_note_id"):
            out.add(str(link["target_note_id"]))
    return out


def _index_counts(index: dict[str, list[str]]) -> dict[str, int]:
    return {
        key: len(value)
        for key, value in sorted(index.items(), key=lambda item: (-len(item[1]), item[0]))
    }


def _top_counts(index: dict[str, list[str]], *, limit: int) -> dict[str, int]:
    return dict(list(_index_counts(index).items())[:limit])


def _entity_type_counts(entity_index: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for bucket in entity_index.values():
        entity_type = str(bucket.get("entity_type") or "concept")
        counts[entity_type] = counts.get(entity_type, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _timeline_bucket_summary(timeline_index: dict[str, list[str]]) -> dict[str, Any]:
    bucket_sizes = sorted((len(ids) for ids in timeline_index.values()), reverse=True)
    return {
        "bucket_count": len(timeline_index),
        "largest_bucket_size": bucket_sizes[0] if bucket_sizes else 0,
        "top_bucket_hashes": [
            {
                "date_hash": _hash(date),
                "note_count": len(ids),
            }
            for date, ids in sorted(timeline_index.items(), key=lambda item: (-len(item[1]), item[0]))[:10]
        ],
    }


def _candidate_reason_type_counts(links: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for link in links:
        for reason in link.get("reasons") or []:
            reason_type = _reason_type(reason)
            counts[reason_type] = counts.get(reason_type, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


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
    parser = argparse.ArgumentParser(description="Build a redacted local report for memory note indexes.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-rows", type=int, default=20000)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--max-links-per-note", type=int, default=5)
    args = parser.parse_args()

    rows = fetch_memory_rows(max_rows=args.max_rows)
    report = build_note_index_report(
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
        "indexed_note_count": report["indexed_note_count"],
        "omitted_non_retrievable_note_count": report["omitted_non_retrievable_note_count"],
        "index_summary": report["index_summary"],
        "coverage": report["coverage"],
        "obsidian_readiness": report["obsidian_readiness"],
        "recommended_next_slice": report["recommended_next_slice"],
    }
    print(json.dumps(printable, indent=2, default=str))
    print()
    print("[OK] wrote " + str(output_path))


if __name__ == "__main__":
    main()
