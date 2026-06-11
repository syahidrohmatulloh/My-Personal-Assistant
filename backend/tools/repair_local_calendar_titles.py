"""Repair malformed titles for confirmed local Calendar events."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.calendar_candidate_extractor import (
    _clean_calendar_event_title,
)
from app.services.supabase_client import safe_execute


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--date")
    args = parser.parse_args()

    def run_query(sb):
        query = (
            sb.table("memories")
            .select(
                "id,calendar_event_title,structured_value,content,"
                "calendar_event_date,calendar_event_status"
            )
            .eq("calendar_event_status", "confirmed_local")
        )

        if args.date:
            query = query.eq("calendar_event_date", args.date)

        return query.limit(1000).execute()

    result = safe_execute(run_query)
    rows = list(result.data or [])
    repairs: list[tuple[str, str]] = []

    for row in rows:
        row_id = str(row.get("id") or "").strip()
        current_title = str(
            row.get("calendar_event_title")
            or row.get("structured_value")
            or row.get("content")
            or ""
        ).strip()

        if not row_id or not current_title:
            continue

        cleaned_title = _clean_calendar_event_title(current_title)

        if (
            not cleaned_title
            or cleaned_title == current_title
            or cleaned_title == "Calendar event"
        ):
            continue

        repairs.append((row_id, cleaned_title))

    print(f"Rows scanned: {len(rows)}")
    print(f"Title repairs found: {len(repairs)}")
    print(f"Apply mode: {args.apply}")

    if not args.apply:
        return

    for row_id, cleaned_title in repairs:
        safe_execute(
            lambda sb, rid=row_id, title=cleaned_title: (
                sb.table("memories")
                .update({"calendar_event_title": title})
                .eq("id", rid)
                .eq("calendar_event_status", "confirmed_local")
                .execute()
            )
        )

    print(f"Title repairs applied: {len(repairs)}")


if __name__ == "__main__":
    main()
