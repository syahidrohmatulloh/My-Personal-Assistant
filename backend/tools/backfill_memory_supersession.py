"""Find and archive existing conflicting single-value memories.

Usage:
  cd backend
  PYTHONPATH=. uv run python tools/backfill_memory_supersession.py --limit 100 --dry-run
  PYTHONPATH=. uv run python tools/backfill_memory_supersession.py --limit 100 --apply
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import re
from typing import Any

from app.services.memory_supersession import decide_supersession, is_single_value_field
from app.services.supabase_client import get_supabase


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def load_candidates(limit: int) -> list[dict[str, Any]]:
    supabase = get_supabase()
    result = (
        supabase.table("memories")
        .select(
            "id,user_id,content,category,structured_field,structured_value,"
            "archived,superseded,deleted_at,created_at,updated_at"
        )
        .eq("archived", False)
        .order("created_at", desc=True)
        .limit(max(limit * 10, limit))
        .execute()
    )

    rows = result.data or []
    out = []
    for row in rows:
        if row.get("deleted_at") or row.get("superseded"):
            continue
        field = clean(row.get("structured_field")).casefold()
        value = clean(row.get("structured_value"))
        if field and value and is_single_value_field(field):
            out.append(row)
    return out[:limit]


def archive(ids: list[str], field: str) -> None:
    if not ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    supabase = get_supabase()
    supabase.table("memories").update(
        {
            "archived": True,
            "superseded": True,
            "archived_by": f"memory_supersession_backfill:{field}",
            "archived_at": now,
            "updated_at": now,
        }
    ).in_("id", ids).execute()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("Use only one of --dry-run or --apply")
    if not args.apply and not args.dry_run:
        raise SystemExit("Choose --dry-run first, then --apply after reviewing output")

    rows = load_candidates(args.limit)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        grouped[(clean(row.get("user_id")), clean(row.get("structured_field")).casefold())].append(row)

    archived_count = 0
    skipped_count = 0

    print(f"Loaded {len(rows)} single-value memory candidates")

    for (user_id, field), group in grouped.items():
        if len(group) <= 1:
            skipped_count += len(group)
            continue

        # Newest first because load_candidates sorts desc. Keep newest.
        newest = group[0]
        newest_value = clean(newest.get("structured_value"))
        old_to_archive = []

        for old in group[1:]:
            decision = decide_supersession(old.get("structured_value"), newest_value)
            if decision.should_supersede:
                old_to_archive.append(clean(old.get("id")))
                print(
                    f"[SUPERSEDE] field={field} keep={clean(newest.get('id'))} "
                    f"archive={clean(old.get('id'))} old={clean(old.get('structured_value'))!r} "
                    f"new={newest_value!r} reason={decision.reason}"
                )
            else:
                skipped_count += 1
                print(
                    f"[SKIP] field={field} old={clean(old.get('structured_value'))!r} "
                    f"new={newest_value!r} reason={decision.reason}"
                )

        if old_to_archive:
            archived_count += len(old_to_archive)
            if args.apply:
                archive(old_to_archive, field)

    print(
        f"Summary: archived={archived_count}, skipped={skipped_count}, "
        f"mode={'apply' if args.apply else 'dry-run'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
