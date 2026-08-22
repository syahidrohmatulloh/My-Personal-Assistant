"""Retrieval evaluation scoring — pure functions, no I/O, no Supabase.

MR0: offline scoring for memory retrieval. A hit is judged by memory ID only.
This module never sees memory content.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryResult:
    query: str
    retrieved_ids: list[str]
    relevant_ids: set[str]
    similarities: list[float] | None = None


@dataclass(frozen=True)
class EvalReport:
    n_queries: int
    recall_at_5: float
    recall_at_10: float
    mrr: float
    hit_rate: float
    mean_first_hit_rank: float | None
    mean_hit_similarity: float | None

    def as_lines(self) -> list[str]:
        def fmt(value: float | None) -> str:
            return "n/a" if value is None else f"{value:.4f}"

        return [
            f"queries:             {self.n_queries}",
            f"recall@5:            {fmt(self.recall_at_5)}",
            f"recall@10:           {fmt(self.recall_at_10)}",
            f"MRR:                 {fmt(self.mrr)}",
            f"hit rate:            {fmt(self.hit_rate)}",
            f"mean first-hit rank: {fmt(self.mean_first_hit_rank)}",
            f"mean hit similarity: {fmt(self.mean_hit_similarity)}",
        ]


def first_hit_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> int | None:
    for index, memory_id in enumerate(retrieved_ids):
        if memory_id in relevant_ids:
            return index + 1
    return None


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 1.0
    if k <= 0:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant_ids) / len(relevant_ids)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    rank = first_hit_rank(retrieved_ids, relevant_ids)
    return 1.0 / rank if rank else 0.0


def mean_similarity_of_hits(result: QueryResult) -> float | None:
    if not result.similarities:
        return None

    scores = [
        float(score)
        for memory_id, score in zip(result.retrieved_ids, result.similarities)
        if memory_id in result.relevant_ids
    ]
    return sum(scores) / len(scores) if scores else None


def evaluate(results: list[QueryResult]) -> EvalReport:
    n_queries = len(results)
    if n_queries == 0:
        return EvalReport(0, 0.0, 0.0, 0.0, 0.0, None, None)

    first_ranks = [
        rank
        for result in results
        if (rank := first_hit_rank(result.retrieved_ids, result.relevant_ids)) is not None
    ]
    hit_similarities = [
        similarity
        for result in results
        if (similarity := mean_similarity_of_hits(result)) is not None
    ]

    return EvalReport(
        n_queries=n_queries,
        recall_at_5=sum(recall_at_k(r.retrieved_ids, r.relevant_ids, 5) for r in results) / n_queries,
        recall_at_10=sum(recall_at_k(r.retrieved_ids, r.relevant_ids, 10) for r in results) / n_queries,
        mrr=sum(reciprocal_rank(r.retrieved_ids, r.relevant_ids) for r in results) / n_queries,
        hit_rate=len(first_ranks) / n_queries,
        mean_first_hit_rank=sum(first_ranks) / len(first_ranks) if first_ranks else None,
        mean_hit_similarity=sum(hit_similarities) / len(hit_similarities) if hit_similarities else None,
    )


# ---------------------------------------------------------------------------
# MR0.2 diagnostics — pure helpers, no I/O, no Supabase
# ---------------------------------------------------------------------------
#
# These helpers make below-threshold near-misses visible for the eval harness.
# Runtime retrieval behavior is not changed here. Production MIN_SIMILARITY
# remains wherever app.services.memory defines it.
#
# Candidate rows passed here must already be safe, IDs/scores only. No memory
# content is required or expected.


@dataclass(frozen=True)
class CandidateCase:
    query: str
    candidates: list[dict]
    relevant_ids: set[str]


@dataclass(frozen=True)
class QueryDiagnostic:
    query: str
    relevant_ids: set[str]
    production_ids: list[str]
    production_hit: bool
    first_hit_rank: int | None
    top_score: float | None
    dropped_relevant: list[dict]
    unfiltered_top_ids: list[str]


def _candidate_id(row: dict) -> str | None:
    value = row.get("id")
    return str(value) if value else None


def _candidate_similarity(row: dict) -> float:
    return float(row.get("similarity", 0.0) or 0.0)


def _candidate_score(row: dict) -> float:
    return float(row.get("retrieval_score", row.get("similarity", 0.0)) or 0.0)


def rank_candidates_at_threshold(
    candidates: list[dict],
    *,
    threshold: float,
    limit: int = 10,
) -> list[dict]:
    """Rank candidate rows at an arbitrary similarity threshold.

    This is for eval only. It does not mutate rows and does not change runtime
    retrieval behavior.
    """
    kept = [
        row
        for row in candidates
        if _candidate_id(row) and _candidate_similarity(row) >= threshold
    ]
    kept.sort(key=lambda row: (_candidate_score(row), _candidate_similarity(row)), reverse=True)
    return kept[:limit]


def query_result_at_threshold(
    *,
    query: str,
    candidates: list[dict],
    relevant_ids: set[str],
    threshold: float,
    limit: int = 10,
) -> QueryResult:
    ranked = rank_candidates_at_threshold(candidates, threshold=threshold, limit=limit)
    return QueryResult(
        query=query,
        retrieved_ids=[str(row["id"]) for row in ranked if row.get("id")],
        relevant_ids=set(relevant_ids),
        similarities=[_candidate_score(row) for row in ranked if row.get("id")],
    )


def threshold_sweep(
    cases: list[CandidateCase],
    thresholds: list[float],
    *,
    limit: int = 10,
) -> dict[float, EvalReport]:
    """Evaluate the same unfiltered candidates at multiple thresholds."""
    reports: dict[float, EvalReport] = {}

    for threshold in thresholds:
        results = [
            query_result_at_threshold(
                query=case.query,
                candidates=case.candidates,
                relevant_ids=case.relevant_ids,
                threshold=threshold,
                limit=limit,
            )
            for case in cases
        ]
        reports[threshold] = evaluate(results)

    return reports


def diagnose_query(
    *,
    query: str,
    relevant_ids: set[str],
    production_ids: list[str],
    unfiltered_candidates: list[dict],
    threshold: float = 0.5,
    limit: int = 10,
) -> QueryDiagnostic:
    """Explain why a labeled query hit or missed under the production filter."""
    production_ids = [str(x) for x in production_ids]
    relevant_ids = {str(x) for x in relevant_ids}
    top_candidates = sorted(
        [row for row in unfiltered_candidates if _candidate_id(row)],
        key=lambda row: (_candidate_score(row), _candidate_similarity(row)),
        reverse=True,
    )[:limit]

    first_rank = first_hit_rank(production_ids, relevant_ids)
    dropped: list[dict] = []

    for row in top_candidates:
        row_id = _candidate_id(row)
        if not row_id or row_id not in relevant_ids:
            continue
        if row_id in production_ids:
            continue
        if _candidate_similarity(row) < threshold:
            dropped.append(
                {
                    "id": row_id,
                    "similarity": _candidate_similarity(row),
                    "retrieval_score": _candidate_score(row),
                }
            )

    top_score = _candidate_score(top_candidates[0]) if top_candidates else None

    return QueryDiagnostic(
        query=query,
        relevant_ids=relevant_ids,
        production_ids=production_ids,
        production_hit=first_rank is not None,
        first_hit_rank=first_rank,
        top_score=top_score,
        dropped_relevant=dropped,
        unfiltered_top_ids=[str(row["id"]) for row in top_candidates if row.get("id")],
    )

