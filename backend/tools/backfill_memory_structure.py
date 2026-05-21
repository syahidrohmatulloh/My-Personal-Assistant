"""Backfill structured memory fields for legacy memories.

Purpose:
- Existing legacy memories may have useful content but missing structured_field
  and structured_value.
- This tool infers safe key/value/category/confidence for those rows.
- It can archive clearly low-value fragments when explicitly requested.

Usage:
  cd backend
  PYTHONPATH=. uv run python tools/backfill_memory_structure.py --limit 100 --dry-run
  PYTHONPATH=. uv run python tools/backfill_memory_structure.py --limit 100 --apply
  PYTHONPATH=. uv run python tools/backfill_memory_structure.py --limit 100 --dry-run --archive-low-value
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import re
from typing import Any

from app.services.memory_hygiene import evaluate_memory_candidate
from app.services.supabase_client import get_supabase


@dataclass(frozen=True)
class InferredStructure:
    structured_field: str
    structured_value: str
    category: str
    confidence: float
    reason: str


SKIP_PREFIXES = (
    "user shared an image:",
    "user uploaded an image:",
    "user asked:",
    "user asked about",
    "user asked whether",
    "user asked how",
    "menurut kamu",
    "coba inget",
    "kamu inget",
)

SAFE_APPLY_REASONS = {
    "body_measurement_height",
    "body_measurement_weight",
    "age",
    "timezone",
    "indonesia_timezone_abbrev",
    "preferred_address",
    "assistant_name",
    "name",
    "preferred_name",
    "location",
    "work_role",
    "employer",
    "language",
    "communication_style",
    "disliked_style",
    "food_preference",
    "sleep_pattern",
    "scheduled_event",
    "active_project",
    "family_member_name",
    "child_name",
    "spouse_name",
    "key_value_colon",
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize(value: Any) -> str:
    text = clean_text(value).casefold()
    text = re.sub(r"[!?.。！？]+$", "", text)
    return text


def token_count(value: str) -> int:
    return len(re.findall(r"[\w@.+:-]+", value.casefold()))


def parse_created_date(value: Any) -> datetime | None:
    raw = clean_text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def resolve_relative_due_date(relative: str, created_at: Any) -> str:
    base = parse_created_date(created_at)
    if base is None:
        return f"relative:{relative}"

    normalized = normalize(relative)
    if normalized == "today":
        return base.date().isoformat()
    if normalized == "tomorrow":
        return (base + timedelta(days=1)).date().isoformat()
    if normalized in {"next week", "minggu depan"}:
        return (base + timedelta(days=7)).date().isoformat()

    return f"relative:{relative}"


def trim_value(value: str) -> str:
    value = clean_text(value)
    value = re.split(
        r"\b(?:and|dan|yang|who|with|dengan|while|karena|because)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return clean_text(value).strip(" ,.;:-")


def infer_structure(content: str, kind: str | None = None, created_at: Any = None) -> InferredStructure | None:
    text = clean_text(content)
    lower = normalize(text)

    if not text:
        return None

    if lower.startswith(SKIP_PREFIXES):
        return None

    # Body/profile measurements.
    measurement_patterns: tuple[tuple[str, str, str, str], ...] = (
        (
            "height",
            r"\b(?:user(?:'s)?\s+)?(?:height|tinggi(?:\s+badan)?)\s+(?:is|adalah|=)?\s*(\d{2,3}(?:[.,]\d+)?)\s*(cm|centimeter|centimeters|m|meter|meters)\b",
            "identity",
            "body_measurement_height",
        ),
        (
            "weight",
            r"\b(?:user(?:'s)?\s+)?(?:weight|berat(?:\s+badan)?)\s+(?:is|adalah|=)?\s*(\d{2,3}(?:[.,]\d+)?)\s*(kg|kilogram|kilograms)\b",
            "identity",
            "body_measurement_weight",
        ),
        (
            "age",
            r"\b(?:user(?:'s)?\s+)?(?:age|umur)\s+(?:is|adalah|=)?\s*(\d{1,3})\s*(?:years old|tahun)?\b",
            "identity",
            "age",
        ),
    )

    for field, pattern, category, reason in measurement_patterns:
        match = re.search(pattern, lower)
        if match:
            number = match.group(1).replace(",", ".")
            unit = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
            value = clean_text(f"{number} {unit}".strip())
            return InferredStructure(field, value, category, 0.90, reason)

    # Timezone.
    timezone_match = re.search(
        r"\b(?:timezone|zona waktu|gmt|utc)\s*(?:is|adalah|=)?\s*(gmt|utc)?\s*([+-]\d{1,2})(?::?(\d{2}))?\b",
        lower,
    )
    if timezone_match:
        prefix = timezone_match.group(1) or "GMT"
        hour = timezone_match.group(2)
        minute = timezone_match.group(3)
        value = f"{prefix.upper()}{hour}"
        if minute:
            value += f":{minute}"
        return InferredStructure("timezone", value, "life_context", 0.90, "timezone")

    zone = re.search(r"\b(wib|wita|wit)\b", lower)
    if zone:
        mapping = {"wib": "GMT+7", "wita": "GMT+8", "wit": "GMT+9"}
        return InferredStructure("timezone", mapping[zone.group(1)], "life_context", 0.88, "indonesia_timezone_abbrev")

    # Preferred address / assistant naming.
    preferred_address_patterns = (
        r"\b(?:user\s+)?(?:wants to be called|ingin dipanggil|mau dipanggil|panggil (?:aku|saya))\s+['\"]?([^'\".,;]+)",
        r"\b(?:user\s+)?(?:calls the assistant)\s+['\"]?([^'\".,;]+)",
    )
    for pattern in preferred_address_patterns:
        match = re.search(pattern, lower)
        if match:
            value = trim_value(match.group(1))
            if value:
                return InferredStructure("preferred_address", value[:120], "preferences", 0.84, "preferred_address")

    assistant_name_match = re.search(
        r"\b(?:user\s+)?(?:wants the ai to be called|wants the assistant to be called|nama assistant|nama asisten)\s+['\"]?([^'\".,;]+)",
        lower,
    )
    if assistant_name_match:
        value = trim_value(assistant_name_match.group(1))
        if value:
            return InferredStructure("assistant_name", value[:120], "preferences", 0.86, "assistant_name")

    # Names / identity.
    identity_patterns: tuple[tuple[str, str, str], ...] = (
        ("preferred_name", r"\b(?:call me|panggil (?:aku|saya))\s+(.+)$", "identity"),
        ("name", r"\b(?:my name is|nama saya|nama aku)\s+(.+)$", "identity"),
    )

    for field, pattern, category in identity_patterns:
        match = re.search(pattern, lower)
        if match:
            value = trim_value(match.group(match.lastindex or 1))
            if value:
                return InferredStructure(field, value[:120], category, 0.82, field)

    # Location / work / role.
    context_patterns: tuple[tuple[str, str, str, str], ...] = (
        ("location", r"\b(?:user\s+)?(?:lives in|tinggal di|domisili di)\s+(.+)$", "life_context", "location"),
        ("work_role", r"\b(?:user\s+)?(?:works as|bekerja sebagai|kerja sebagai)\s+(.+)$", "work", "work_role"),
        ("employer", r"\b(?:user\s+)?(?:works at|bekerja di|kerja di)\s+(.+)$", "work", "employer"),
        ("language", r"\b(?:user\s+)?(?:speaks|berbicara bahasa|menggunakan bahasa)\s+(.+)$", "preferences", "language"),
    )

    for field, pattern, category, reason in context_patterns:
        match = re.search(pattern, lower)
        if match:
            value = trim_value(match.group(1))
            if value:
                return InferredStructure(field, value[:160], category, 0.82, reason)

    # Active project / durable workstream.
    active_project_patterns: tuple[str, ...] = (
        r"\buser is working on an?\s+(.+?project\s+with\s+.+?)(?:$|[.,;])",
        r"\buser is working on\s+(.+?project\s+with\s+.+?)(?:$|[.,;])",
        r"\buser is working on an?\s+(.+?project)(?:$|[.,;])",
        r"\buser is working on\s+(.+?project)(?:$|[.,;])",
        r"\buser works on\s+(.+?-related projects?)(?:$|[.,;])",
    )

    for pattern in active_project_patterns:
        match = re.search(pattern, lower)
        if match:
            # Do not use trim_value() here because durable project names can
            # legitimately contain "with", e.g. "project with Institutional Grade..."
            value = clean_text(match.group(1)).strip(" ,.;:-")
            if value and token_count(value) >= 3:
                return InferredStructure("active_project", value[:240], "goals", 0.80, "active_project")

    # Food or drink preference. Allow single-item preferences such as mangoes.
    food_like_match = re.search(
        r"\b(?:user\s+)?(?:likes|suka)\s+([^().,;]+)(?:\s*\(([^)]{2,80})\))?",
        lower,
    )
    if food_like_match:
        main = trim_value(food_like_match.group(1))
        alias = trim_value(food_like_match.group(2) or "")
        if main and 1 <= token_count(main) <= 8:
            value = f"{main} ({alias})" if alias else main
            return InferredStructure("food_preference", value[:180], "preferences", 0.80, "food_preference")

    # Scheduled / time-bound event. Store as memory for now; later this can feed Calendar.
    scheduled_event_patterns: tuple[str, ...] = (
        r"\buser has an?\s+(.+?)\s+scheduled for\s+(today|tomorrow|next week|minggu depan)\b",
        r"\buser has\s+(.+?)\s+scheduled for\s+(today|tomorrow|next week|minggu depan)\b",
    )

    for pattern in scheduled_event_patterns:
        match = re.search(pattern, lower)
        if match:
            event_name = trim_value(match.group(1))
            relative = trim_value(match.group(2))
            if event_name and token_count(event_name) >= 3:
                due_date = resolve_relative_due_date(relative, created_at)
                value = f"{event_name} | due_date={due_date} | relative={relative}"
                return InferredStructure("scheduled_event", value[:260], "goals", 0.76, "scheduled_event")

    # Sleep pattern / recent sleep habit.
    sleep_patterns: tuple[tuple[str, str], ...] = (
        ("often_stays_up_late", r"\b(?:user\s+)?(?:often|frequently|usually|tends to)\s+(?:stays up late|sleeps late)\b"),
        ("often_stays_up_late", r"\b(?:user\s+)?sering\s+(?:begadang|tidur larut|bangun larut malam)\b"),
        ("currently_stays_up_late", r"\b(?:user\s+)?(?:masih|recently|akhir-akhir ini)\s+(?:bangun larut malam|bangun malam|begadang|tidur larut)\b"),
    )

    for value, pattern in sleep_patterns:
        if re.search(pattern, lower):
            return InferredStructure("sleep_pattern", value, "preferences", 0.78, "sleep_pattern")

    # Preferences.
    preference_patterns: tuple[tuple[str, str, str], ...] = (
        ("communication_style", r"\b(?:user\s+)?(?:prefers|lebih suka|suka)\s+(?:answers?|jawaban)?\s*(.+)$", "preferences"),
        ("communication_style", r"\b(?:user\s+)?(?:prefers varied emoji usage|likes varied emoji usage)\s*(.*)$", "preferences"),
        ("disliked_style", r"\b(?:user\s+)?(?:does not like|doesn't like|tidak suka|nggak suka|ga suka|not use)\s+(.+)$", "preferences"),
        ("food_preference", r"\b(?:user\s+)?(?:likes|suka)\s+(.+?)(?:\s+\(|$)", "preferences"),
        ("preference", r"\b(?:user\s+)?(?:prefers|lebih prefer|lebih suka)\s+(.+)$", "preferences"),
    )

    for field, pattern, category in preference_patterns:
        match = re.search(pattern, lower)
        if match:
            value = trim_value(match.group(1))
            if value and token_count(value) >= 2:
                return InferredStructure(field, value[:220], category, 0.78, field)

    # Relationship names. Avoid capturing descriptions after "and/yang/with".
    relationship_patterns: tuple[tuple[str, str], ...] = (
        ("child_name", r"\b(?:user(?:'s)?\s+)?(?:daughter|son|child|anak)\s+(?:is named|named|bernama|namanya)\s+([^,.;]+)"),
        ("family_member_name", r"\b(?:user\s+)?(?:has a family member named)\s+([^,.;]+)"),
        ("spouse_name", r"\b(?:user(?:'s)?\s+)?(?:wife|husband|spouse|istri|suami)\s+(?:is named|named|bernama|namanya)\s+([^,.;]+)"),
    )

    for field, pattern in relationship_patterns:
        match = re.search(pattern, lower)
        if match:
            value = trim_value(match.group(1))
            if value and 1 <= token_count(value) <= 4:
                return InferredStructure(field, value[:140], "relationships", 0.82, field)

    # Meeting / deadline facts. Avoid generic key:value parser for time strings like 17:00.
    meeting_match = re.search(r"\buser has a meeting(?: scheduled)? with\s+(.+?)(?:\s+at\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?))?(?:\s+to\s+(.+))?$", lower)
    if meeting_match:
        with_whom = trim_value(meeting_match.group(1))
        meeting_time = clean_text(meeting_match.group(2) or "")
        topic = trim_value(meeting_match.group(3) or "")
        value_parts = [part for part in [with_whom, meeting_time, topic] if part]
        if value_parts:
            return InferredStructure("upcoming_meeting", " | ".join(value_parts)[:240], "work", 0.74, "meeting")

    # Content already follows "key: value", but skip likely narrative/image prefixes and time-only colon.
    if ":" in text and not re.search(r"\b\d{1,2}:\d{2}\b", text):
        key, value = text.split(":", 1)
        key_norm = re.sub(r"[^a-z0-9_]+", "_", normalize(key)).strip("_")
        value_clean = clean_text(value)
        if (
            len(key_norm) >= 2
            and value_clean
            and key_norm not in {"user_shared_an_image", "image", "screenshot"}
        ):
            return InferredStructure(key_norm[:80], value_clean[:240], infer_category(key_norm), 0.74, "key_value_colon")

    # Generic useful legacy facts. This is intentionally conservative.
    if token_count(text) >= 6 and not lower.endswith("?"):
        hygiene = evaluate_memory_candidate(
            content=text,
            structured_field="legacy_fact",
            structured_value=text,
            category=infer_category(str(kind or "context")),
            confidence=0.62,
        )
        if hygiene.should_store:
            inferred_kind = normalize(kind or "context") or "context"
            if inferred_kind in {"fact", "context", "preference", "plan"}:
                field = "legacy_" + re.sub(r"[^a-z0-9_]+", "_", inferred_kind).strip("_")
                return InferredStructure(field[:80], text[:300], infer_category(field), 0.62, "legacy_content_value")

    return None


def infer_category(field: str) -> str:
    key = normalize(field)
    if key in {"height", "weight", "age", "name", "preferred_name"}:
        return "identity"
    if "timezone" in key or "location" in key:
        return "life_context"
    if "meeting" in key or "employer" in key or "work" in key:
        return "work"
    if "style" in key or "preference" in key or "address" in key or "food" in key or "assistant_name" in key or "sleep" in key:
        return "preferences"
    if "child" in key or "spouse" in key or "wife" in key or "husband" in key or "family" in key:
        return "relationships"
    if "goal" in key:
        return "goals"
    if "routine" in key:
        return "routines"
    return "life_context"


def should_consider(row: dict[str, Any]) -> bool:
    if bool(row.get("archived")) or bool(row.get("superseded")):
        return False
    if row.get("deleted_at"):
        return False

    field = clean_text(row.get("structured_field"))
    value = clean_text(row.get("structured_value"))

    return not field or not value


def load_candidates(limit: int) -> list[dict[str, Any]]:
    supabase = get_supabase()
    result = (
        supabase.table("memories")
        .select(
            "id,user_id,content,kind,category,structured_field,structured_value,"
            "confidence,archived,superseded,deleted_at,updated_at,created_at"
        )
        .order("created_at", desc=True)
        .limit(max(limit * 4, limit))
        .execute()
    )

    rows = result.data or []
    return [row for row in rows if should_consider(row)][:limit]


def update_memory(memory_id: str, inferred: InferredStructure) -> None:
    now = datetime.now(timezone.utc).isoformat()
    supabase = get_supabase()
    (
        supabase.table("memories")
        .update(
            {
                "structured_field": inferred.structured_field,
                "structured_value": inferred.structured_value,
                "category": inferred.category,
                "confidence": inferred.confidence,
                "updated_at": now,
            }
        )
        .eq("id", memory_id)
        .execute()
    )


def archive_memory(memory_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    supabase = get_supabase()
    (
        supabase.table("memories")
        .update(
            {
                "archived": True,
                "archived_by": "memory_structure_backfill_low_value",
                "archived_at": now,
                "updated_at": now,
            }
        )
        .eq("id", memory_id)
        .execute()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--archive-low-value",
        action="store_true",
        help="Archive active rows that cannot be inferred and are rejected by hygiene.",
    )
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Also apply broad legacy_* fallback inferences. Off by default for safety.",
    )
    args = parser.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("Use only one of --dry-run or --apply")

    if not args.apply and not args.dry_run:
        raise SystemExit("Choose --dry-run first, then --apply after reviewing output")

    rows = load_candidates(args.limit)

    inferred_count = 0
    archived_count = 0
    skipped_count = 0

    print(f"Loaded {len(rows)} candidate memories")

    for row in rows:
        memory_id = str(row.get("id"))
        content = clean_text(row.get("content"))
        inferred = infer_structure(content, row.get("kind"), row.get("created_at"))

        if inferred:
            is_safe_reason = inferred.reason in SAFE_APPLY_REASONS
            if not is_safe_reason and not args.include_legacy:
                skipped_count += 1
                print(
                    f"[SKIP_UNSAFE_INFERENCE] {memory_id} | {content[:90]!r} -> "
                    f"{inferred.category}.{inferred.structured_field} "
                    f"reason={inferred.reason}; rerun with --include-legacy if you really want this"
                )
                continue

            inferred_count += 1
            print(
                f"[INFER] {memory_id} | {content[:90]!r} -> "
                f"{inferred.category}.{inferred.structured_field} = {inferred.structured_value!r} "
                f"confidence={inferred.confidence:.2f} reason={inferred.reason}"
            )
            if args.apply:
                update_memory(memory_id, inferred)
            continue

        hygiene = evaluate_memory_candidate(content=content)
        if args.archive_low_value and not hygiene.should_store:
            archived_count += 1
            print(f"[ARCHIVE_LOW_VALUE] {memory_id} | {content[:90]!r} reason={hygiene.reason}")
            if args.apply:
                archive_memory(memory_id)
            continue

        skipped_count += 1
        print(f"[SKIP] {memory_id} | {content[:90]!r}")

    print(
        "Summary: "
        f"inferred={inferred_count}, "
        f"archived_low_value={archived_count}, "
        f"skipped={skipped_count}, "
        f"mode={'apply' if args.apply else 'dry-run'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
