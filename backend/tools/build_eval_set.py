"""MR0.1 — Private eval-set builder (local, read-only).

Turns "capture a retrieval baseline" from hand-copying UUIDs out of Supabase
into a two-minute loop, feeding the MR0 harness (tools/eval_retrieval.py).

Safety contract (do not weaken):
  - READ-ONLY. Never inserts/updates/deletes any memory.
  - Reuses the existing get_supabase() service client and settings — no new
    credential handling.
  - Memory CONTENT is shown ONLY in your terminal, redacted, so you can choose
    relevant IDs. Content is NEVER written to any file.
  - The only file written is backend/eval/retrieval_eval.local.json (gitignored).
    It contains user_id, query, relevant_ids, and optional notes — IDs only.

Typical loop:

    cd backend
    # 1) see candidate memories for a query (redacted preview + IDs), pick relevant IDs:
    uv run python tools/build_eval_set.py --user-id <uuid> --query "what coffee do i like" --limit 10
    # 2) record the labeled query into the local eval set:
    uv run python tools/build_eval_set.py --user-id <uuid> --query "what coffee do i like" \
        --relevant-ids <id1>,<id2> --notes "prefers no sugar"
    # 3) repeat for ~30-50 queries, then run the MR0 harness live:
    uv run python tools/eval_retrieval.py --eval-set eval/retrieval_eval.local.json

Flags: --user-id, --query, --relevant-ids, --expect-empty, --limit, --notes, --output, --dry-run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUTPUT = BACKEND_ROOT / "eval" / "retrieval_eval.local.json"


def _redact(content: str, width: int = 72) -> str:
    """Short, single-line preview for terminal selection only. Never persisted."""
    text = " ".join(str(content or "").split())
    if len(text) > width:
        text = text[: width - 1].rstrip() + "…"
    return text


async def _suggest(user_id: str, query: str, limit: int) -> list[dict]:
    """Run the real retrieval path read-only to list candidate memories."""
    from app.services.memory import retrieve_relevant

    rows = await retrieve_relevant(user_id, query, limit=limit)
    out = []
    for r in rows:
        out.append(
            {
                "id": str(r.get("id")),
                "score": float(r.get("retrieval_score", r.get("similarity", 0.0)) or 0.0),
                "preview": _redact(r.get("content", "")),
            }
        )
    return out


def _load_output(path: Path, user_id: str) -> dict:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("queries"), list):
            data["queries"] = []
        if user_id and not data.get("user_id"):
            data["user_id"] = user_id
        return data
    return {"user_id": user_id, "queries": []}


def _write_output(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="MR0.1 private eval-set builder (read-only)")
    p.add_argument("--user-id", help="User UUID whose memories to query.")
    p.add_argument("--query", required=True, help="The eval query text.")
    p.add_argument(
        "--relevant-ids",
        help="Comma-separated memory IDs that SHOULD surface for --query. "
        "If given, the query is recorded to the eval set. If omitted, the tool "
        "only previews candidates so you can choose them.",
    )
    p.add_argument(
        "--expect-empty",
        action="store_true",
        help="Record a negative probe: this query should not retrieve any memory.",
    )
    p.add_argument("--limit", type=int, default=10, help="Preview depth (default 10).")
    p.add_argument("--notes", help="Optional note stored with the query (no content).")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Eval set path (gitignored).")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be recorded without writing the file.",
    )
    args = p.parse_args()

    record_mode = args.relevant_ids is not None or bool(args.expect_empty)

    if args.expect_empty and args.relevant_ids is not None:
        print("[error] use either --expect-empty or --relevant-ids, not both.")
        return 2

    if record_mode and not args.user_id:
        print("[error] recording a query requires --user-id (the eval set is per-user).")
        return 2

    if not record_mode:
        if not args.user_id:
            print("[error] previewing candidates requires --user-id.")
            return 2
        try:
            candidates = asyncio.run(_suggest(args.user_id, args.query, args.limit))
        except Exception as exc:  # noqa: BLE001
            print(f"[error] retrieval failed (check backend env / Supabase): {exc}")
            return 1
        if not candidates:
            print("No candidates returned. Try a different query or check the user_id.")
            return 0
        print(f'Candidates for: "{args.query}"  (terminal-only preview, content not saved)\n')
        for c in candidates:
            print(f"  {c['id']}  score={c['score']:.4f}  {c['preview']}")
        print(
            "\nPick the relevant IDs, then re-run with:\n"
            f'  --user-id {args.user_id} --query "{args.query}" '
            "--relevant-ids <id1>,<id2>"
        )
        return 0

    if args.expect_empty:
        relevant_ids = []
    else:
        relevant_ids = [x.strip() for x in str(args.relevant_ids).split(",") if x.strip()]
        if not relevant_ids:
            print("[error] --relevant-ids was empty. Use --expect-empty for negative probes.")
            return 2

    entry = {"query": args.query, "relevant_ids": relevant_ids}
    if args.expect_empty:
        entry["expect_empty"] = True
    if args.notes:
        entry["notes"] = args.notes

    data = _load_output(args.output, args.user_id)
    replaced = False
    for i, q in enumerate(data["queries"]):
        if str(q.get("query")) == args.query:
            data["queries"][i] = entry
            replaced = True
            break
    if not replaced:
        data["queries"].append(entry)

    if args.dry_run:
        print("[dry-run] would record (no file written):")
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        print(f"[dry-run] target: {args.output}  (total queries would be {len(data['queries'])})")
        return 0

    _write_output(args.output, data)
    print(f"Recorded {'(updated)' if replaced else '(new)'}: \"{args.query}\" "
          f"→ {len(relevant_ids)} relevant id(s)")
    print(f"Eval set now has {len(data['queries'])} query(ies): {args.output}")
    print("When you have ~30-50, run: uv run python tools/eval_retrieval.py "
          "--eval-set eval/retrieval_eval.local.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
