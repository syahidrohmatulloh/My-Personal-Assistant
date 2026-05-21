"""Backfill lifecycle metadata for time-bound memories.

Usage:
  cd backend
  PYTHONPATH=. uv run python tools/backfill_time_bound_memories.py --limit 100 --dry-run
  PYTHONPATH=. uv run python tools/backfill_time_bound_memories.py --limit 100 --apply

Archive expired time-bound memories:
  PYTHONPATH=. uv run python tools/backfill_time_bound_memories.py --limit 100 --dry-run --archive-expired
  PYTHONPATH=. uv run python tools/backfill_time_bound_memories.py --limit 100 --apply --archive-expired
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import re
from typing import Any

from app.services.supabase_client import get_supabase
from app.services.time_bound_memory import infer_time_bound_metadata, should_archive_time_bound_memory


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def load_candidates(limit: int) -> list[dict[str, Any]]:
    supabase = get_supabase()
    result = (
        supabase.table("memories")
        .select(
            "id,user_id,content,kind,category,structured_field,structured_value,"
            "archived,superseded,deleted_at,status,lifecycle_type,due_date,expires_at,calendar_candidate,"
            "created_at,updated_at"
        )
        .eq("archived", False)
        .order("created_at", desc=True)
        .limit(max(limit * 5, limit))
        .execute()
    )

    rows = result.data or []
    out = []
    for row in rows:
        if row.get("deleted_at") or row.get("superseded"):
            continue
        field = clean(row.get("structured_field")).casefold()
        lifecycle_type = clean(row.get("lifecycle_type")).casefold()
        if field in {"scheduled_event", "upcoming_meeting"} or lifecycle_type == "time_bound":
            out.append(row)
    return out[:limit]


def update_lifecycle(memory_id: str, meta) -> None:
    now = datetime.now(timezone.utc).isoformat()
    supabase = get_supabase()
    supabase.table("memories").update(
        {
            "lifecycle_type": meta.lifecycle_type,
            "due_date": meta.due_date,
            "expires_at": meta.expires_at,
            "calendar_candidate": meta.calendar_candidate,
            "updated_at": now,
        }
    ).eq("id", memory_id).execute()


def archive_memory(memory_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    supabase = get_supabase()
    supabase.table("memories").update(
        {
            "archived": True,
            "archived_by": "time_bound_memory_expired",
            "archived_at": now,
            "updated_at": now,
        }
    ).eq("id", memory_id).execute()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--archive-expired", action="store_true")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("Use only one of --dry-run or --apply")
    if not args.apply and not args.dry_run:
        raise SystemExit("Choose --dry-run first, then --apply after reviewing output")

    rows = load_candidates(args.limit)

    updated = 0
    archived = 0
    skipped = 0

    print(f"Loaded {len(rows)} time-bound candidates")

    for row in rows:
        memory_id = clean(row.get("id"))
        content = clean(row.get("content"))
        meta = infer_time_bound_metadata(row)

        if meta:
            updated += 1
            print(
                f"[LIFECYCLE] {memory_id} | {content[:90]!r} -> "
                f"lifecycle_type={meta.lifecycle_type} due_date={meta.due_date} "
                f"expires_at={meta.expires_at} calendar_candidate={meta.calendar_candidate} "
                f"reason={meta.reason}"
            )
            if args.apply:
                update_lifecycle(memory_id, meta)

            # If user explicitly asks to archive expired, apply after metadata update.
            row_for_archive = dict(row)
            row_for_archive["lifecycle_type"] = meta.lifecycle_type
            row_for_archive["expires_at"] = meta.expires_at

            if args.archive_expired and should_archive_time_bound_memory(row_for_archive):
                archived += 1
                print(f"[ARCHIVE_EXPIRED] {memory_id} | {content[:90]!r}")
                if args.apply:
                    archive_memory(memory_id)
            continue

        if args.archive_expired and should_archive_time_bound_memory(row):
            archived += 1
            print(f"[ARCHIVE_EXPIRED] {memory_id} | {content[:90]!r}")
            if args.apply:
                archive_memory(memory_id)
            continue

        skipped += 1
        print(f"[SKIP] {memory_id} | {content[:90]!r}")

    print(
        f"Summary: lifecycle_updated={updated}, archived_expired={archived}, "
        f"skipped={skipped}, mode={'apply' if args.apply else 'dry-run'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
