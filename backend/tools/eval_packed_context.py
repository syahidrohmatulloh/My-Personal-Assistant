#!/usr/bin/env python3
"""Evaluate which retrieved memories survive prompt packing.

This complements tools/eval_retrieval.py:
- eval_retrieval.py checks retrieval quality;
- eval_packed_context.py checks final prompt-context quality.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.memory import retrieve_relevant
from app.services.memory_context_packer import pack_memory_context_for_prompt
from app.services.packed_context_eval import PackedContextCaseResult, evaluate_packed_context


def _load_eval_set(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "queries" not in data or not isinstance(data["queries"], list):
        raise SystemExit("[error] eval set must contain a queries list")
    if not data.get("user_id"):
        raise SystemExit("[error] eval set must contain user_id")

    return data


def _ids(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    out: list[str] = []
    for row in rows:
        value = row.get("id") or row.get("memory_id")
        if value:
            out.append(str(value))
    return tuple(out)


async def _run(args: argparse.Namespace) -> int:
    data = _load_eval_set(Path(args.eval_set))
    user_id = str(data["user_id"])

    results: list[PackedContextCaseResult] = []

    print("\nPer-query packed-context diagnostics\n")

    for index, item in enumerate(data["queries"], start=1):
        query = str(item.get("query") or "")
        relevant_ids = tuple(str(x) for x in item.get("relevant_ids", []))
        expect_empty = bool(item.get("expect_empty"))

        rows = await retrieve_relevant(user_id, query, limit=args.retrieval_limit)
        packed = pack_memory_context_for_prompt(
            legacy_memories=rows,
            related_summaries=[],
            query_text=query,
        )

        result = PackedContextCaseResult(
            query=query,
            relevant_ids=relevant_ids,
            retrieved_ids=_ids(rows),
            packed_ids=tuple(packed.memory_ids),
            expect_empty=expect_empty,
        )
        results.append(result)

        print(f"{index}. {query}")
        print(f"   relevant:       {', '.join(relevant_ids) if relevant_ids else '-'}")
        print(f"   retrieved_ids:  {', '.join(result.retrieved_ids) if result.retrieved_ids else '-'}")
        print(f"   packed_ids:     {', '.join(result.packed_ids) if result.packed_ids else '-'}")
        if expect_empty:
            print("   expect empty:   yes")
            print(f"   false positive: {'yes' if result.false_positive else 'no'}")
        else:
            print(f"   retrieval hit:  {'yes' if result.retrieval_hit else 'no'}")
            print(f"   packed hit:     {'yes' if result.packed_hit else 'no'}")
            rank = result.packed_first_hit_rank
            print(f"   packed rank:    {rank if rank is not None else '-'}")
            print(f"   packed recall:  {result.packed_recall:.4f}")
        print(f"   packed_count:   {packed.memory_count}")
        print(f"   packed_chars:   {packed.total_chars}")
        print(f"   intent:         {packed.intent}\n")

    report = evaluate_packed_context(results)

    print("Packed-context report\n")
    print(f"  positive queries:          {report.positive_queries}")
    print(f"  retrieval hit rate:        {report.retrieval_hit_rate:.4f}")
    print(f"  packed hit rate:           {report.packed_hit_rate:.4f}")
    print(f"  packed MRR:                {report.packed_mrr:.4f}")
    print(f"  mean packed recall:        {report.mean_packed_recall:.4f}")
    print(f"  negative queries:          {report.negative_queries}")
    print(f"  negative false positives:  {report.negative_false_positives}")

    if args.strict:
        failed = False
        if report.positive_queries and report.packed_hit_rate < 1.0:
            print("[FAIL] strict mode requires packed hit rate 1.0000")
            failed = True
        if report.negative_false_positives:
            print("[FAIL] strict mode requires zero negative false positives")
            failed = True
        if failed:
            return 1
        print("[OK] strict packed-context checks passed")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", required=True)
    parser.add_argument("--retrieval-limit", type=int, default=12)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
