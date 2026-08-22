"""Offline retrieval eval harness for MR0/MR0.2.

Runs the existing production retrieval path by default:
- app.services.memory.retrieve_relevant
- match_memories RPC
- Voyage embeddings
- Ranking 2.0

MR0.2 adds tooling-only diagnostics:
- --diagnostics fetches unfiltered RPC candidates read-only.
- --thresholds performs a read-only sweep over candidate thresholds.
- Production MIN_SIMILARITY is NOT changed.

The eval set is judged by memory IDs only. Do not commit private memory content.

Usage:
    cd backend
    uv run python tools/eval_retrieval.py
    uv run python tools/eval_retrieval.py --eval-set eval/retrieval_eval.local.json
    uv run python tools/eval_retrieval.py --eval-set eval/retrieval_eval.local.json --diagnostics
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.retrieval_eval import (
    CandidateCase,
    QueryResult,
    diagnose_query,
    evaluate,
    threshold_sweep,
)

SAMPLE_PATH = BACKEND_ROOT / "eval" / "sample_eval_set.json"
DEFAULT_THRESHOLDS = "0.30,0.35,0.40,0.45,0.50"


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
    """Dry-run mode echoes relevant_ids as if perfectly retrieved."""
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


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _embed_query_text(query: str) -> list[float]:
    """Use the existing embeddings module without adding new credentials.

    Function names changed over time in this codebase, so this tries the known
    query/text embedding entry points conservatively.
    """
    from app.services import embeddings

    candidates = (
        "embed_query",
        "embed_user_message",
        "embed_search_query",
        "embed_text",
    )

    last_error: Exception | None = None

    for name in candidates:
        fn = getattr(embeddings, name, None)
        if not callable(fn):
            continue

        try:
            value = await _maybe_await(fn(query))
        except TypeError as exc:
            last_error = exc
            continue

        if isinstance(value, dict) and isinstance(value.get("embedding"), list):
            return value["embedding"]
        if isinstance(value, list) and value and isinstance(value[0], (int, float)):
            return value
        if isinstance(value, list) and value and isinstance(value[0], list):
            return value[0]

    raise RuntimeError(
        "Could not find a compatible query embedding function in app.services.embeddings"
        + (f": {last_error}" if last_error else "")
    )


def _rpc_payloads(*, user_id: str, embedding: list[float], limit: int) -> list[dict[str, Any]]:
    """Try the known match_memories argument shapes used across migrations."""
    return [
        {
            "p_user_id": user_id,
            "p_query_embedding": embedding,
            "p_match_count": limit,
        },
        {
            "user_id": user_id,
            "query_embedding": embedding,
            "match_count": limit,
        },
        {
            "p_user_id": user_id,
            "query_embedding": embedding,
            "match_count": limit,
        },
        {
            "target_user_id": user_id,
            "query_embedding": embedding,
            "match_count": limit,
        },
        {
            "user_id": user_id,
            "embedding": embedding,
            "match_count": limit,
        },
        {
            "p_user_id": user_id,
            "embedding": embedding,
            "match_count": limit,
        },
    ]


def _safe_similarity(row: dict[str, Any]) -> float:
    return float(row.get("similarity", row.get("score", 0.0)) or 0.0)


def _sanitize_candidate(row: dict[str, Any]) -> dict[str, Any]:
    """Keep IDs/scores/metadata only; never carry memory content into diagnostics."""
    return {
        "id": str(row.get("id") or ""),
        "similarity": _safe_similarity(row),
        "retrieval_score": float(
            row.get("retrieval_score", row.get("similarity", row.get("score", 0.0))) or 0.0
        ),
        "kind": row.get("kind"),
        "category": row.get("category"),
        "structured_field": row.get("structured_field"),
        "source": row.get("source"),
        "created_at": row.get("created_at"),
        "last_confirmed_at": row.get("last_confirmed_at"),
        "confidence": row.get("confidence"),
        "source_priority": row.get("source_priority"),
        "salience": row.get("salience"),
        "archived": row.get("archived"),
        "superseded": row.get("superseded"),
        "deleted_at": row.get("deleted_at"),
        "status": row.get("status"),
    }


async def fetch_unfiltered_candidates(
    *,
    user_id: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Read-only diagnostic fetch: same RPC candidates, before 0.5 filtering."""
    from app.services import memory
    from app.services.supabase_client import get_supabase

    embedding = await _embed_query_text(query)
    sb = get_supabase()

    last_error: Exception | None = None
    rows: list[dict[str, Any]] | None = None

    for payload in _rpc_payloads(user_id=user_id, embedding=embedding, limit=limit):
        try:
            result = sb.rpc("match_memories", payload).execute()
            rows = list(result.data or [])
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if rows is None:
        raise RuntimeError(f"match_memories RPC failed for all known payload shapes: {last_error}")

    is_active = getattr(memory, "_mi_is_active_memory", None)
    score_fn = getattr(memory, "memory_retrieval_score", None)

    candidates: list[dict[str, Any]] = []
    for row in rows:
        if callable(is_active) and not is_active(row):
            continue

        safe_row = _sanitize_candidate(row)

        if callable(score_fn):
            try:
                safe_row["retrieval_score"] = float(score_fn(row))
            except Exception:  # noqa: BLE001
                safe_row["retrieval_score"] = safe_row["similarity"]

        if safe_row.get("id"):
            candidates.append(safe_row)

    candidates.sort(
        key=lambda row: (
            float(row.get("retrieval_score", 0.0) or 0.0),
            float(row.get("similarity", 0.0) or 0.0),
        ),
        reverse=True,
    )
    return candidates


async def run_live(
    *,
    user_id: str,
    queries: list[dict[str, Any]],
    top_k: int,
) -> list[QueryResult]:
    """Call the real production retrieval path per query."""
    from app.services.memory import retrieve_relevant

    results: list[QueryResult] = []

    for item in queries:
        query = str(item["query"])
        relevant_ids = {str(value) for value in item.get("relevant_ids", [])}
        rows = await retrieve_relevant(user_id, query, limit=top_k)

        rows_with_id = [row for row in rows if row.get("id")]

        results.append(
            QueryResult(
                query=query,
                retrieved_ids=[str(row["id"]) for row in rows_with_id],
                relevant_ids=relevant_ids,
                similarities=[
                    float(row.get("retrieval_score", row.get("similarity", 0.0)) or 0.0)
                    for row in rows_with_id
                ],
            )
        )

    return results


async def run_diagnostics(
    *,
    user_id: str,
    queries: list[dict[str, Any]],
    top_k: int,
    raw_limit: int,
    thresholds: list[float],
) -> None:
    from app.services.memory import retrieve_relevant

    production_results: list[QueryResult] = []
    candidate_cases: list[CandidateCase] = []

    print("\nPer-query diagnostics\n")

    for index, item in enumerate(queries, 1):
        query = str(item["query"])
        relevant_ids = {str(value) for value in item.get("relevant_ids", [])}

        production_rows = await retrieve_relevant(user_id, query, limit=top_k)
        production_ids = [str(row["id"]) for row in production_rows if row.get("id")]
        production_scores = [
            float(row.get("retrieval_score", row.get("similarity", 0.0)) or 0.0)
            for row in production_rows
            if row.get("id")
        ]

        unfiltered = await fetch_unfiltered_candidates(
            user_id=user_id,
            query=query,
            limit=max(raw_limit, top_k),
        )

        production_results.append(
            QueryResult(
                query=query,
                retrieved_ids=production_ids,
                relevant_ids=relevant_ids,
                similarities=production_scores,
            )
        )
        candidate_cases.append(
            CandidateCase(
                query=query,
                candidates=unfiltered,
                relevant_ids=relevant_ids,
            )
        )

        diagnostic = diagnose_query(
            query=query,
            relevant_ids=relevant_ids,
            production_ids=production_ids,
            unfiltered_candidates=unfiltered,
            threshold=0.5,
            limit=raw_limit,
        )

        print(f"{index}. {query}")
        print(f"   relevant:        {', '.join(sorted(relevant_ids)) or '-'}")
        print(f"   production hit:  {'yes' if diagnostic.production_hit else 'no'}")
        print(f"   first rank:      {diagnostic.first_hit_rank or '-'}")
        print(f"   top score:       {diagnostic.top_score:.4f}" if diagnostic.top_score is not None else "   top score:       -")
        print(f"   production ids:  {', '.join(production_ids) or '-'}")
        print(f"   unfiltered top:  {', '.join(diagnostic.unfiltered_top_ids[:5]) or '-'}")

        if diagnostic.dropped_relevant:
            print("   dropped relevant below 0.50:")
            for row in diagnostic.dropped_relevant:
                print(
                    "     "
                    f"{row['id']} sim={row['similarity']:.4f} "
                    f"score={row['retrieval_score']:.4f}"
                )
        else:
            print("   dropped relevant below 0.50: -")
        print()

    report = evaluate(production_results)
    print("Production-filter report\n")
    for line in report.as_lines():
        print("  " + line)

    print("\nRead-only threshold sweep\n")
    print("  threshold  recall@5  recall@10  MRR     hit_rate  mean_rank")
    reports = threshold_sweep(candidate_cases, thresholds, limit=top_k)
    for threshold in sorted(reports):
        r = reports[threshold]
        mean_rank = "n/a" if r.mean_first_hit_rank is None else f"{r.mean_first_hit_rank:.4f}"
        print(
            f"  {threshold:>8.2f}  "
            f"{r.recall_at_5:>8.4f}  "
            f"{r.recall_at_10:>9.4f}  "
            f"{r.mrr:>6.4f}  "
            f"{r.hit_rate:>8.4f}  "
            f"{mean_rank:>9}"
        )

    print(
        "\nThis sweep is diagnostic only. It does not change production MIN_SIMILARITY."
    )


def _parse_thresholds(raw: str) -> list[float]:
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(float(part))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="MR0 offline retrieval eval harness")
    parser.add_argument(
        "--eval-set",
        type=Path,
        default=SAMPLE_PATH,
        help="Path to eval JSON. Default uses committed synthetic sample.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Retrieval depth for live eval.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip live retrieval and validate metrics only.",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Show per-query retrieval diagnostics and a read-only threshold sweep.",
    )
    parser.add_argument(
        "--thresholds",
        default=DEFAULT_THRESHOLDS,
        help="Comma-separated thresholds for --diagnostics sweep.",
    )
    parser.add_argument(
        "--raw-limit",
        type=int,
        default=30,
        help="Unfiltered candidate depth for diagnostics.",
    )

    args = parser.parse_args()

    if not args.eval_set.exists():
        print(f"[error] eval set not found: {args.eval_set}")
        print("Create backend/eval/retrieval_eval.local.json from the sample.")
        return 2

    data = load_eval_set(args.eval_set)
    queries = data["queries"]
    user_id = str(data.get("user_id") or "").strip()
    is_sample = args.eval_set.resolve() == SAMPLE_PATH.resolve()

    if args.diagnostics:
        if is_sample:
            print("[error] diagnostics require a live local eval set, not the synthetic sample.")
            return 2
        if not user_id:
            print("[error] diagnostics need user_id in the eval set.")
            return 2
        asyncio.run(
            run_diagnostics(
                user_id=user_id,
                queries=queries,
                top_k=args.top_k,
                raw_limit=args.raw_limit,
                thresholds=_parse_thresholds(args.thresholds),
            )
        )
        return 0

    if args.dry_run or is_sample:
        if is_sample and not args.dry_run:
            print(
                "[note] using committed synthetic sample; running dry-run metrics. "
                "Use --eval-set eval/retrieval_eval.local.json for live numbers.\n"
            )
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

    print(
        "\nRecord this as the MR0 baseline before changing chunking, hybrid retrieval, "
        "context packing, or reranking."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
