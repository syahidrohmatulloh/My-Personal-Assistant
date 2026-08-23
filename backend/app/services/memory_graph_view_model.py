
from __future__ import annotations

from typing import Any

from app.services.memory_note_index import build_note_index


def build_memory_graph_view_model(
    notes: list[dict[str, Any]],
    *,
    retrievable_only: bool = True,
    max_links_per_note: int = 5,
    note_preview_chars: int = 180,
) -> dict[str, Any]:
    """Build a UI-ready Obsidian-like view model from projected memory notes.

    Pure/read-only:
    - no DB access
    - no writes
    - no embeddings
    - no retrieval behavior changes
    """

    index = build_note_index(
        notes,
        retrievable_only=retrievable_only,
        max_links_per_note=max_links_per_note,
    )
    note_by_id = {
        str(note.get("id")): note
        for note in notes
        if note.get("id") and str(note.get("id")) in (index.get("note_refs") or {})
    }

    related_map = _related_note_map(index.get("candidate_links") or [])

    note_cards = [
        build_note_card(
            note,
            related_note_ids=related_map.get(note_id, []),
            preview_chars=note_preview_chars,
        )
        for note_id, note in sorted(note_by_id.items())
    ]

    return {
        "version": "M6",
        "read_only": True,
        "runtime_retrieval_change": False,
        "schema_migration": False,
        "summary": {
            "input_note_count": len(notes),
            "visible_note_count": len(note_cards),
            "tag_section_count": len(index.get("tag_index") or {}),
            "entity_section_count": len(index.get("entity_index") or {}),
            "timeline_section_count": len(index.get("timeline_index") or {}),
            "candidate_link_count": len(index.get("candidate_links") or []),
        },
        "sections": {
            "notes": note_cards,
            "types": build_type_sections(index.get("type_index") or {}, note_by_id),
            "tags": build_tag_sections(index.get("tag_index") or {}, note_by_id),
            "entities": build_entity_sections(index.get("entity_index") or {}, note_by_id),
            "timeline": build_timeline_sections(index.get("timeline_index") or {}, note_by_id),
            "candidate_backlinks": build_candidate_backlink_sections(index.get("candidate_links") or []),
        },
    }


def build_note_card(
    note: dict[str, Any],
    *,
    related_note_ids: list[str] | None = None,
    preview_chars: int = 180,
) -> dict[str, Any]:
    source = note.get("source") or {}
    lifecycle = note.get("lifecycle") or {}

    return {
        "id": str(note.get("id") or ""),
        "title": str(note.get("title") or "").strip(),
        "body_preview": _preview(note.get("body"), limit=preview_chars),
        "note_type": str(note.get("note_type") or "fact"),
        "tags": list(note.get("tags") or []),
        "entity_count": len(note.get("entities") or []),
        "timeline_date": note.get("timeline_date"),
        "has_temporal_anchor": bool(note.get("has_temporal_anchor")),
        "source": {
            "source": source.get("source"),
            "has_source_conversation_id": bool(source.get("source_conversation_id")),
            "has_evidence": bool(source.get("has_evidence")),
            "evidence_count": int(source.get("evidence_count") or 0),
        },
        "lifecycle": {
            "status": lifecycle.get("status") or "active",
            "retrievable": bool(lifecycle.get("retrievable", True)),
            "archived": bool(lifecycle.get("archived")),
            "superseded": bool(lifecycle.get("superseded")),
            "deleted": bool(lifecycle.get("deleted")),
        },
        "related_note_ids": list(related_note_ids or []),
    }


def build_type_sections(type_index: dict[str, list[str]], note_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": note_type,
            "count": len(_existing_note_ids(note_ids, note_by_id)),
            "note_ids": _existing_note_ids(note_ids, note_by_id),
        }
        for note_type, note_ids in sorted(type_index.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def build_tag_sections(tag_index: dict[str, list[str]], note_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "tag": tag,
            "count": len(_existing_note_ids(note_ids, note_by_id)),
            "note_ids": _existing_note_ids(note_ids, note_by_id),
        }
        for tag, note_ids in sorted(tag_index.items(), key=lambda item: (-len(item[1]), item[0]))
        if _existing_note_ids(note_ids, note_by_id)
    ]


def build_entity_sections(entity_index: dict[str, dict[str, Any]], note_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    sections = []
    for entity_key, bucket in entity_index.items():
        note_ids = _existing_note_ids(bucket.get("note_ids") or [], note_by_id)
        if not note_ids:
            continue
        sections.append(
            {
                "entity_key": entity_key,
                "entity_type": bucket.get("entity_type") or "concept",
                "entity_name": bucket.get("entity_name") or "",
                "count": len(note_ids),
                "note_ids": note_ids,
            }
        )
    return sorted(sections, key=lambda item: (-item["count"], item["entity_type"], item["entity_name"]))


def build_timeline_sections(timeline_index: dict[str, list[str]], note_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    sections = []
    for date, note_ids in timeline_index.items():
        existing_ids = _existing_note_ids(note_ids, note_by_id)
        if not existing_ids:
            continue
        sections.append(
            {
                "date": date,
                "count": len(existing_ids),
                "note_ids": existing_ids,
            }
        )
    return sorted(sections, key=lambda item: item["date"])


def build_candidate_backlink_sections(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_note_id": str(link.get("source_note_id") or ""),
            "target_note_id": str(link.get("target_note_id") or ""),
            "score": link.get("score"),
            "reasons": list(link.get("reasons") or []),
        }
        for link in links
        if link.get("source_note_id") and link.get("target_note_id")
    ]


def _related_note_map(links: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for link in links:
        source = str(link.get("source_note_id") or "")
        target = str(link.get("target_note_id") or "")
        if not source or not target:
            continue
        out.setdefault(source, []).append(target)
        out.setdefault(target, []).append(source)

    for note_id, related in list(out.items()):
        out[note_id] = sorted(set(related))
    return out


def _existing_note_ids(note_ids: list[str], note_by_id: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(str(note_id) for note_id in note_ids if str(note_id) in note_by_id)


def _preview(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
