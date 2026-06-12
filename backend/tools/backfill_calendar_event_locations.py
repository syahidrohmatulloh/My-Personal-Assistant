"""Backfill calendar_event_location for existing calendar records.

Derives a location from legacy unstructured fields (structured_value /
content) and writes it to the dedicated calendar_event_location column.

Strictly limited:
- Updates ONLY calendar_event_location. Titles, dates, timestamps,
  Google sync fields, and reminders (proactive_nudges) are never touched.
- Only rows whose calendar_event_location is currently empty are considered.
- Dry-run by default; pass --apply to write.

Usage:
    python tools/backfill_calendar_event_locations.py --date 2026-06-14
    python tools/backfill_calendar_event_locations.py --date 2026-06-14 --apply
    python tools/backfill_calendar_event_locations.py            # all dates, dry run
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.calendar_candidate_extractor import _extract_location_hint
from app.services.supabase_client import safe_execute


def derive_location(structured_value: str | None, content: str | None) -> str | None:
    """Best-effort location from legacy text fields.

    Priority:
    1. legacy pipe format:      ... | location=Rainbow Hills
    2. human structured format: Calendar event: ...; location Rainbow Hills
    3. content suffix:          ... on 2026-06-14 at Rainbow Hills
    4. conservative hint:       ... golf di Rainbow Hills dengan Indosat ...
    """
    structured = str(structured_value or "").strip()
    body = str(content or "").strip()

    legacy = re.search(r"\blocation=([^|]+)", structured, flags=re.IGNORECASE)
    if legacy:
        value = legacy.group(1).strip()
        if value:
            return value[:180]

    human = re.search(r";\s*location\s+(.+?)\s*(?:;|$)", structured, flags=re.IGNORECASE)
    if human:
        value = human.group(1).strip()
        if value:
            return value[:180]

    content_at = re.search(
        r"\bon\s+\d{4}-\d{2}-\d{2}\s+at\s+(.+)$", body, flags=re.IGNORECASE
    )
    if content_at:
        value = content_at.group(1).strip().rstrip(".")
        if value:
            return value[:180]

    for source in (structured, body):
        hint = _extract_location_hint(source)
        if hint:
            return hint[:180]

    return None


def apply_backfills(backfills: list[tuple[str, str, str]]) -> tuple[int, int]:
    """Apply guarded location updates and return (applied, skipped_concurrent).

    Returned rows are explicitly requested with ``select("id")`` so the
    result distinguishes a successful guarded update from a row that no
    longer matches because another process populated its location first.
    """
    applied = 0
    skipped_concurrent = 0

    for row_id, _title, location in backfills:
        result = safe_execute(
            lambda sb, _id=row_id, _loc=location: sb.table("memories")
            .update({"calendar_event_location": _loc})
            .eq("id", _id)
            .or_("calendar_event_location.is.null,calendar_event_location.eq.")
            .select("id")
            .execute()
        )
        if list(result.data or []):
            applied += 1
        else:
            skipped_concurrent += 1

    return applied, skipped_concurrent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument("--date", help="Limit to calendar_event_date (YYYY-MM-DD)")
    args = parser.parse_args()

    def run_query(sb):
        query = (
            sb.table("memories")
            .select(
                "id,calendar_event_title,calendar_event_location,"
                "calendar_event_date,calendar_event_status,calendar_candidate,"
                "structured_value,content"
            )
            .or_("calendar_candidate.eq.true,calendar_event_status.in.(confirmed_local,synced_google)")
        )

        if args.date:
            query = query.eq("calendar_event_date", args.date)

        return query.limit(1000).execute()

    result = safe_execute(run_query)
    rows = list(result.data or [])

    backfills: list[tuple[str, str, str]] = []  # (id, title, location)
    skipped_existing = 0
    skipped_no_location = 0

    for row in rows:
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            continue

        if str(row.get("calendar_event_location") or "").strip():
            skipped_existing += 1
            continue

        location = derive_location(row.get("structured_value"), row.get("content"))
        if not location:
            skipped_no_location += 1
            continue

        title = str(row.get("calendar_event_title") or "").strip()[:60]
        backfills.append((row_id, title, location))

    print(f"Scanned: {len(rows)} calendar rows")
    print(f"Already have a location: {skipped_existing}")
    print(f"No derivable location:   {skipped_no_location}")
    print(f"Backfill candidates:     {len(backfills)}")

    for row_id, title, location in backfills:
        print(f"  - {row_id[:8]}  {title or '(untitled)'}  ->  {location}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write calendar_event_location.")
        return

    applied, skipped_concurrent = apply_backfills(backfills)

    print(f"\nApplied: {applied} row(s) updated (calendar_event_location only).")
    if skipped_concurrent:
        print(f"Skipped: {skipped_concurrent} row(s) gained a location after the scan and were left untouched.")


if __name__ == "__main__":
    main()
