"""Offline retrieval eval harness for MR0.

Usage:
    cd backend
    uv run python tools/eval_retrieval.py
    uv run python tools/eval_retrieval.py --eval-set eval/retrieval_eval.local.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.retrieval_eval import QueryResult, evaluate

SAMPLE_PATH = BACKEND_ROOT / "eval" / "sample_eval_set.json"


def load_eval_set(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("eval set must be a JSON object")

    queries = data.get("queries")
    if not isinstance(queries, list):
        raise ValueError("eval set must contain a queries list")

    for index, item in enumerate(queries):
        if not isinstance(item, dict):
            raise ValueError(f"query item #{index + 1} must be an object")
        if not str(item.get("query") or "").strip():
            raise ValueError(f"query item #{index + 1} is missing query")
        if not isinstance(item.get("relevant_ids"), list):
            raise ValueError(f"query item #{index + 1} is missing relevant_ids list")

    return data


def run_dry(queries: list[dict[str, Any]]) -> list[QueryResult]:
    results: list[QueryResult] = []
    for item in queries:
        relevant_ids = [str(value) for value in item.get("relevant_ids", [])]
        results.append(
            QueryResult(
                query=str(item["query"]),
                retrieved_ids=list(relevant_ids),
                relevant_ids=set(relevant_ids),
                similarities=[1.0] * len(relevant_ids),
            )
        )
    return results


async def run_live(*, user_id: str, queries: list[dict[str, Any]], top_k: int) -> list[QueryResult]:
    from app.services.memory import retrieve_relevant

    results: list[QueryResult] = []
    for item in queries:
        rows = await retrieve_relevant(user_id, str(item["query"]), limit=top_k)
        rows_with_id = [row for row in rows if row.get("id")]

        results.append(
            QueryResult(
                query=str(item["query"]),
                retrieved_ids=[str(row["id"]) for row in rows_with_id],
                relevant_ids={str(value) for value in item.get("relevant_ids", [])},
                similarities=[
                    float(row.get("retrieval_score", row.get("similarity", 0.0)) or 0.0)
                    for row in rows_with_id
                ],
            )
        )

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="MR0 offline retrieval eval harness")
    parser.add_argument("--eval-set", type=Path, default=SAMPLE_PATH)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.eval_set.exists():
        print(f"[error] eval set not found: {args.eval_set}")
        print("Create backend/eval/retrieval_eval.local.json from the sample.")
        return 2

    data = load_eval_set(args.eval_set)
    queries = data["queries"]
    user_id = str(data.get("user_id") or "").strip()
    is_sample = args.eval_set.resolve() == SAMPLE_PATH.resolve()

    if args.dry_run or is_sample:
        if is_sample and not args.dry_run:
            print("[note] using committed synthetic sample; running dry-run metrics.\n")
        results = run_dry(queries)
        mode = "dry-run"
    else:
        if not user_id:
            print("[error] live eval needs user_id in the eval set.")
            return 2
        results = asyncio.run(run_live(user_id=user_id, queries=queries, top_k=args.top_k))
        mode = "live"

    report = evaluate(results)

    print(f"Retrieval eval — {mode}\n")
    for line in report.as_lines():
        print("  " + line)

    print("\nRecord this as the MR0 baseline before changing chunking, hybrid retrieval, context packing, or reranking.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
