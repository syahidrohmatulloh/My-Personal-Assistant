
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


TEMPORAL_TERMS = (
    "today",
    "tomorrow",
    "yesterday",
    "tonight",
    "this week",
    "last week",
    "next week",
    "hari ini",
    "besok",
    "kemarin",
    "minggu ini",
    "minggu depan",
    "bulan ini",
    "pagi",
    "siang",
    "sore",
    "malam",
    "wib",
    "gmt",
    "utc",
)

ENTITY_FIELD_TYPES = {
    "name": "person",
    "child_name": "person",
    "family_member_name": "person",
    "assistant_name": "assistant",
    "active_project": "project",
    "active_goal_reference": "goal",
    "scheduled_event": "event",
    "location": "place",
    "preferred_address": "place",
}

TAG_RULES = [
    ("family", ("anak", "child", "istri", "wife", "ayah", "family", "zahra")),
    ("identity", ("nama", "name", "birthday", "ulang tahun", "timezone", "wib", "gmt", "height")),
    ("work", ("bank", "mandiri", "meeting", "client", "project", "corporate", "coverage")),
    ("calendar", ("meeting", "schedule", "jadwal", "besok", "pagi", "siang", "sore", "malam", "calendar")),
    ("goal", ("goal", "target", "focus", "mau", "ingin", "want", "plan")),
    ("preference", ("suka", "prefer", "preference", "favorite", "tone", "style")),
    ("food", ("food", "makan", "restaurant", "kopi", "coffee")),
    ("travel", ("trip", "travel", "flight", "hotel", "visa", "umrah")),
    ("health", ("sleep", "tidur", "mood", "stress", "energy", "gym", "fitness")),
    ("project", ("project", "repo", "backend", "frontend", "aliyya", "assistant")),
]


@dataclass(frozen=True)
class ProjectedEntity:
    name: str
    entity_type: str
    source: str
    confidence: float = 0.85


@dataclass(frozen=True)
class ProjectedSource:
    source: str | None
    source_conversation_id: str | None
    has_evidence: bool
    evidence_count: int


@dataclass(frozen=True)
class ProjectedLifecycle:
    status: str
    archived: bool
    superseded: bool
    deleted: bool
    retrievable: bool
    superseded_by: str | None = None


@dataclass(frozen=True)
class ProjectedMemoryNote:
    id: str
    title: str
    body: str
    note_type: str
    tags: list[str] = field(default_factory=list)
    entities: list[ProjectedEntity] = field(default_factory=list)
    source: ProjectedSource | None = None
    lifecycle: ProjectedLifecycle | None = None
    timeline_date: str | None = None
    has_temporal_anchor: bool = False
    linked_note_ids: list[str] = field(default_factory=list)


def project_memory_row(row: dict[str, Any]) -> dict[str, Any]:
    """Project one memories row into an Obsidian-like note object.

    This is intentionally pure/read-only:
    - no DB access
    - no embedding calls
    - no retrieval changes
    - no writes/migrations
    """

    content = _as_text(row.get("content"))
    note_type = infer_note_type(row)
    tags = infer_tags(row, note_type=note_type)
    entities = infer_entities(row)
    source = ProjectedSource(
        source=_clean_optional(row.get("source")),
        source_conversation_id=_clean_optional(row.get("source_conversation_id")),
        has_evidence=_evidence_count(row.get("evidence")) > 0,
        evidence_count=_evidence_count(row.get("evidence")),
    )
    lifecycle = ProjectedLifecycle(
        status=_as_text(row.get("status") or "active"),
        archived=_as_bool(row.get("archived")),
        superseded=_as_bool(row.get("superseded")),
        deleted=bool(row.get("deleted_at")),
        retrievable=is_retrievable_memory(row),
        superseded_by=_clean_optional(row.get("superseded_by")),
    )
    note = ProjectedMemoryNote(
        id=_as_text(row.get("id")),
        title=infer_title(row, note_type=note_type),
        body=content,
        note_type=note_type,
        tags=tags,
        entities=entities,
        source=source,
        lifecycle=lifecycle,
        timeline_date=infer_timeline_date(row),
        has_temporal_anchor=has_temporal_anchor(row),
        linked_note_ids=[],
    )
    return _note_to_dict(note)


def project_memory_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [project_memory_row(row) for row in rows]


def summarize_note_projection(notes: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_tag: dict[str, int] = {}
    entity_count = 0
    timeline_count = 0
    retrievable_count = 0

    for note in notes:
        note_type = str(note.get("note_type") or "fact")
        by_type[note_type] = by_type.get(note_type, 0) + 1

        for tag in note.get("tags") or []:
            tag = str(tag)
            by_tag[tag] = by_tag.get(tag, 0) + 1

        entity_count += len(note.get("entities") or [])
        if note.get("timeline_date") or note.get("has_temporal_anchor"):
            timeline_count += 1
        lifecycle = note.get("lifecycle") or {}
        if lifecycle.get("retrievable"):
            retrievable_count += 1

    return {
        "total_notes": len(notes),
        "by_type": dict(sorted(by_type.items(), key=lambda item: (-item[1], item[0]))),
        "top_tags": dict(sorted(by_tag.items(), key=lambda item: (-item[1], item[0]))[:30]),
        "entity_count": entity_count,
        "timeline_note_count": timeline_count,
        "retrievable_note_count": retrievable_count,
    }


def infer_note_type(row: dict[str, Any]) -> str:
    kind = _fold(row.get("kind"))
    category = _fold(row.get("category"))
    structured_field = _fold(row.get("structured_field"))
    lifecycle_type = _fold(row.get("lifecycle_type"))
    calendar_status = _fold(row.get("calendar_event_status"))
    content = _fold(row.get("content"))
    text = " ".join([content, kind, category, structured_field, lifecycle_type, calendar_status])

    if structured_field == "scheduled_event" or lifecycle_type == "time_bound" or calendar_status:
        return "event"
    if category == "goals" or kind == "plan" or structured_field in {"active_goal_reference", "monthly_focus"}:
        return "goal"
    if category == "identity" or structured_field in {"name", "birthday", "timezone", "height", "assistant_name"}:
        return "identity"
    if category == "relationships" or structured_field in {"child_name", "family_member_name"}:
        return "relationship"
    if category == "routines" or "routine" in text or "habit" in text or structured_field == "sleep_pattern":
        return "routine"
    if category == "preferences" or kind == "preference" or "prefer" in text or "suka" in text:
        return "preference"
    if category == "constraints":
        return "constraint"
    if "project" in text or "repo" in text or "backend" in text or "frontend" in text:
        return "project"
    return "fact"


def infer_title(row: dict[str, Any], *, note_type: str | None = None) -> str:
    calendar_title = _clean_optional(row.get("calendar_event_title"))
    if calendar_title:
        return _truncate_title(calendar_title)

    structured_field = _clean_optional(row.get("structured_field"))
    structured_value = _clean_optional(row.get("structured_value"))
    if structured_field and structured_value:
        return _truncate_title(f"{_humanize_key(structured_field)}: {structured_value}")

    content = _clean_optional(row.get("content"))
    if content:
        return _truncate_title(content)

    return _humanize_key(note_type or "memory")


def infer_tags(row: dict[str, Any], *, note_type: str | None = None) -> list[str]:
    text = " ".join(
        [
            _as_text(row.get("content")),
            _as_text(row.get("kind")),
            _as_text(row.get("category")),
            _as_text(row.get("structured_field")),
            _as_text(row.get("lifecycle_type")),
            _as_text(row.get("calendar_event_status")),
            _as_text(row.get("calendar_event_title")),
        ]
    ).lower()

    tags: list[str] = []
    if note_type:
        tags.append("type:" + note_type)

    for tag, needles in TAG_RULES:
        if any(needle in text for needle in needles):
            tags.append(tag)

    category = _clean_optional(row.get("category"))
    if category:
        tags.append("category:" + category.lower())

    structured_field = _clean_optional(row.get("structured_field"))
    if structured_field:
        tags.append("field:" + structured_field.lower())

    if has_temporal_anchor(row):
        tags.append("timeline")

    return _unique(tags)[:12]


def infer_entities(row: dict[str, Any]) -> list[ProjectedEntity]:
    entities: list[ProjectedEntity] = []

    field_name = _fold(row.get("structured_field"))
    structured_value = _clean_optional(row.get("structured_value"))
    if field_name in ENTITY_FIELD_TYPES and structured_value:
        entities.append(
            ProjectedEntity(
                name=structured_value,
                entity_type=ENTITY_FIELD_TYPES[field_name],
                source="structured_field:" + field_name,
                confidence=0.9,
            )
        )

    calendar_title = _clean_optional(row.get("calendar_event_title"))
    if calendar_title:
        entities.append(
            ProjectedEntity(
                name=calendar_title,
                entity_type="event",
                source="calendar_event_title",
                confidence=0.8,
            )
        )

    return _dedupe_entities(entities)


def infer_timeline_date(row: dict[str, Any]) -> str | None:
    for key in ("calendar_event_date", "due_date"):
        value = _clean_optional(row.get(key))
        if value:
            return value[:10]
    for key in ("calendar_event_start_at", "expires_at", "created_at"):
        value = _clean_optional(row.get(key))
        if value and len(value) >= 10:
            return value[:10]
    return None


def has_temporal_anchor(row: dict[str, Any]) -> bool:
    if infer_timeline_date(row):
        return True
    content = _fold(row.get("content"))
    if any(term in content for term in TEMPORAL_TERMS):
        return True
    return any(ch.isdigit() for ch in content)


def is_retrievable_memory(row: dict[str, Any]) -> bool:
    if row.get("deleted_at"):
        return False
    if _as_bool(row.get("archived")):
        return False
    if _as_bool(row.get("superseded")):
        return False
    return _fold(row.get("status") or "active") == "active"


def _note_to_dict(note: ProjectedMemoryNote) -> dict[str, Any]:
    data = asdict(note)
    data["entities"] = [asdict(entity) for entity in note.entities]
    data["source"] = asdict(note.source) if note.source else None
    data["lifecycle"] = asdict(note.lifecycle) if note.lifecycle else None
    return data


def _evidence_count(value: Any) -> int:
    if isinstance(value, list):
        return len([item for item in value if item])
    if isinstance(value, dict):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip() else 0
    return 0


def _dedupe_entities(entities: list[ProjectedEntity]) -> list[ProjectedEntity]:
    seen: set[tuple[str, str]] = set()
    out: list[ProjectedEntity] = []
    for entity in entities:
        key = (entity.entity_type, entity.name.strip().lower())
        if not entity.name.strip() or key in seen:
            continue
        seen.add(key)
        out.append(entity)
    return out


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        value = _as_text(value).strip()
        if value and value not in out:
            out.append(value)
    return out


def _clean_optional(value: Any) -> str | None:
    text = _as_text(value).strip()
    return text or None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _fold(value: Any) -> str:
    return _as_text(value).strip().lower()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _truncate_title(value: str, *, limit: int = 72) -> str:
    text = " ".join(_as_text(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _humanize_key(value: str) -> str:
    return " ".join(part for part in _as_text(value).strip("_").split("_") if part).title()
