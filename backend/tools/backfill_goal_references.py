"""Backfill duplicate goal memories into lightweight active goal references.

Usage:
  cd backend
  PYTHONPATH=. uv run python tools/backfill_goal_references.py --limit 100 --dry-run
  PYTHONPATH=. uv run python tools/backfill_goal_references.py --limit 100 --apply
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import re
from typing import Any

from app.services.goal_source_rules import decide_goal_reference, convert_row_to_goal_reference
from app.services.supabase_client import get_supabase


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def load_active_goals(user_id: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    result = (
        supabase.table("goals")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    return result.data or []


def load_candidates(limit: int) -> list[dict[str, Any]]:
    supabase = get_supabase()
    result = (
        supabase.table("memories")
        .select(
            "id,user_id,content,kind,category,structured_field,structured_value,"
            "confidence,source,source_priority,archived,superseded,deleted_at,created_at,updated_at"
        )
        .eq("archived", False)
        .order("created_at", desc=True)
        .limit(max(limit * 5, limit))
        .execute()
    )

    rows = result.data or []
    candidates = []
    for row in rows:
        if row.get("deleted_at") or row.get("superseded"):
            continue
        field = clean(row.get("structured_field"))
        category = clean(row.get("category")).casefold()
        kind = clean(row.get("kind")).casefold()
        content = clean(row.get("content")).casefold()

        looks_relevant = (
            category == "goals"
            or kind == "plan"
            or "goal" in content
            or "training" in content
            or "consistent" in content
            or "konsisten" in content
            or "olahraga" in content
        )

        if looks_relevant and field != "active_goal_reference":
            candidates.append(row)

    return candidates[:limit]


def update_memory(memory_id: str, converted: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    supabase = get_supabase()
    supabase.table("memories").update(
        {
            "content": converted["content"],
            "kind": converted["kind"],
            "category": converted["category"],
            "structured_field": converted["structured_field"],
            "structured_value": converted["structured_value"],
            "confidence": converted["confidence"],
            "source_priority": converted["source_priority"],
            "updated_at": now,
        }
    ).eq("id", memory_id).execute()


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
    goals_by_user: dict[str, list[dict[str, Any]]] = {}

    converted_count = 0
    skipped_count = 0

    print(f"Loaded {len(rows)} goal-memory candidates")

    for row in rows:
        user_id = clean(row.get("user_id"))
        memory_id = clean(row.get("id"))
        content = clean(row.get("content"))

        if not user_id:
            skipped_count += 1
            print(f"[SKIP] {memory_id} missing user_id")
            continue

        if user_id not in goals_by_user:
            goals_by_user[user_id] = load_active_goals(user_id)

        decision = decide_goal_reference(row, goals_by_user[user_id])
        if not decision.should_convert:
            skipped_count += 1
            print(f"[SKIP] {memory_id} | {content[:90]!r} reason={decision.reason} score={decision.score:.2f}")
            continue

        converted = convert_row_to_goal_reference(row, decision)
        converted_count += 1
        print(
            f"[CONVERT] {memory_id} | {content[:90]!r} -> "
            f"{converted['structured_field']} = {converted['structured_value']!r} "
            f"score={decision.score:.2f}"
        )

        if args.apply:
            update_memory(memory_id, converted)

    print(
        f"Summary: converted={converted_count}, skipped={skipped_count}, "
        f"mode={'apply' if args.apply else 'dry-run'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
