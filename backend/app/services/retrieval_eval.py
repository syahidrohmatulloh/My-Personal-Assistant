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
