
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


GENERIC_LINK_TAG_PREFIXES = ("type:", "category:")
GENERIC_LINK_TAGS = {"timeline", "calendar"}


@dataclass(frozen=True)
class NoteLinkCandidate:
    source_note_id: str
    target_note_id: str
    score: float
    reasons: list[str]


def build_note_index(
    notes: list[dict[str, Any]],
    *,
    retrievable_only: bool = True,
    max_links_per_note: int = 5,
) -> dict[str, Any]:
    selected_notes = [
        note
        for note in notes
        if _note_id(note) and (not retrievable_only or _is_retrievable(note))
    ]

    tag_index: dict[str, list[str]] = {}
    entity_index: dict[str, dict[str, Any]] = {}
    timeline_index: dict[str, list[str]] = {}
    type_index: dict[str, list[str]] = {}
    note_refs: dict[str, dict[str, Any]] = {}

    for note in selected_notes:
        note_id = _note_id(note)
        note_type = _note_type(note)
        tags = _tags(note)
        entities = _entities(note)
        timeline_date = _timeline_date(note)

        note_refs[note_id] = {
            "id": note_id,
            "note_type": note_type,
            "tag_count": len(tags),
            "entity_count": len(entities),
            "timeline_date": timeline_date,
            "has_temporal_anchor": bool(note.get("has_temporal_anchor")),
            "retrievable": _is_retrievable(note),
        }

        type_index.setdefault(note_type, []).append(note_id)

        for tag in tags:
            tag_index.setdefault(tag, []).append(note_id)

        for entity in entities:
            key = entity_key(entity)
            if not key:
                continue
            bucket = entity_index.setdefault(
                key,
                {
                    "entity_key": key,
                    "entity_type": _entity_type(entity),
                    "entity_name": _entity_name(entity),
                    "note_ids": [],
                },
            )
            bucket["note_ids"].append(note_id)

        if timeline_date:
            timeline_index.setdefault(timeline_date, []).append(note_id)

    _sort_index_values(tag_index)
    _sort_index_values(timeline_index)
    _sort_index_values(type_index)
    for bucket in entity_index.values():
        bucket["note_ids"] = sorted(set(bucket["note_ids"]))

    candidate_links = build_candidate_links(
        selected_notes,
        max_links_per_note=max_links_per_note,
    )

    return {
        "total_input_notes": len(notes),
        "indexed_note_count": len(selected_notes),
        "retrievable_only": retrievable_only,
        "note_refs": note_refs,
        "type_index": dict(sorted(type_index.items())),
        "tag_index": dict(sorted(tag_index.items())),
        "entity_index": dict(sorted(entity_index.items())),
        "timeline_index": dict(sorted(timeline_index.items())),
        "candidate_links": [asdict(link) for link in candidate_links],
    }


def build_candidate_links(
    notes: list[dict[str, Any]],
    *,
    max_links_per_note: int = 5,
    minimum_score: float = 2.0,
) -> list[NoteLinkCandidate]:
    candidates: list[NoteLinkCandidate] = []

    for left_idx, left in enumerate(notes):
        left_id = _note_id(left)
        if not left_id:
            continue

        for right in notes[left_idx + 1 :]:
            right_id = _note_id(right)
            if not right_id:
                continue

            score, reasons = candidate_link_score(left, right)
            if score < minimum_score:
                continue

            candidates.append(
                NoteLinkCandidate(
                    source_note_id=left_id,
                    target_note_id=right_id,
                    score=round(score, 3),
                    reasons=reasons,
                )
            )

    candidates.sort(
        key=lambda item: (
            -item.score,
            item.source_note_id,
            item.target_note_id,
        )
    )
    return _cap_links_per_note(candidates, max_links_per_note=max_links_per_note)


def candidate_link_score(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    left_entities = {entity_key(entity) for entity in _entities(left)}
    right_entities = {entity_key(entity) for entity in _entities(right)}
    shared_entities = sorted(key for key in left_entities.intersection(right_entities) if key)
    for key in shared_entities:
        score += 3.0
        reasons.append("entity:" + key)

    left_date = _timeline_date(left)
    right_date = _timeline_date(right)
    if left_date and right_date and left_date == right_date:
        score += 1.5
        reasons.append("timeline:" + left_date)

    shared_tags = sorted(_linkable_tags(left).intersection(_linkable_tags(right)))
    for tag in shared_tags:
        score += 1.0
        reasons.append("tag:" + tag)

    return score, reasons


def entity_key(entity: dict[str, Any]) -> str:
    entity_type = _normalize_key(_entity_type(entity))
    entity_name = _normalize_key(_entity_name(entity))
    if not entity_type or not entity_name:
        return ""
    return entity_type + ":" + entity_name


def _cap_links_per_note(
    candidates: list[NoteLinkCandidate],
    *,
    max_links_per_note: int,
) -> list[NoteLinkCandidate]:
    if max_links_per_note <= 0:
        return []

    counts: dict[str, int] = {}
    out: list[NoteLinkCandidate] = []

    for candidate in candidates:
        left_count = counts.get(candidate.source_note_id, 0)
        right_count = counts.get(candidate.target_note_id, 0)
        if left_count >= max_links_per_note or right_count >= max_links_per_note:
            continue
        out.append(candidate)
        counts[candidate.source_note_id] = left_count + 1
        counts[candidate.target_note_id] = right_count + 1

    return out


def _linkable_tags(note: dict[str, Any]) -> set[str]:
    tags = set()
    for tag in _tags(note):
        folded = tag.strip().lower()
        if not folded or folded in GENERIC_LINK_TAGS:
            continue
        if any(folded.startswith(prefix) for prefix in GENERIC_LINK_TAG_PREFIXES):
            continue
        tags.add(folded)
    return tags


def _note_id(note: dict[str, Any]) -> str:
    return str(note.get("id") or "").strip()


def _note_type(note: dict[str, Any]) -> str:
    return str(note.get("note_type") or "fact").strip() or "fact"


def _tags(note: dict[str, Any]) -> list[str]:
    raw = note.get("tags") or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for tag in raw:
        value = str(tag or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def _entities(note: dict[str, Any]) -> list[dict[str, Any]]:
    raw = note.get("entities") or []
    if not isinstance(raw, list):
        return []
    return [entity for entity in raw if isinstance(entity, dict)]


def _entity_type(entity: dict[str, Any]) -> str:
    return str(entity.get("entity_type") or "concept").strip() or "concept"


def _entity_name(entity: dict[str, Any]) -> str:
    return str(entity.get("name") or "").strip()


def _timeline_date(note: dict[str, Any]) -> str | None:
    value = note.get("timeline_date")
    if not value:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text


def _is_retrievable(note: dict[str, Any]) -> bool:
    lifecycle = note.get("lifecycle") or {}
    if not isinstance(lifecycle, dict):
        return True
    return bool(lifecycle.get("retrievable", True))


def _normalize_key(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _sort_index_values(index: dict[str, list[str]]) -> None:
    for key, values in list(index.items()):
        index[key] = sorted(set(values))
