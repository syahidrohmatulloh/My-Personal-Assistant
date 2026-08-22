"""Pure evaluation helpers for packed memory context.

This evaluates what survives prompt packing, not just what retrieval returned.
No database or network I/O belongs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PackedContextCaseResult:
    query: str
    relevant_ids: tuple[str, ...]
    retrieved_ids: tuple[str, ...]
    packed_ids: tuple[str, ...]
    expect_empty: bool = False

    @property
    def retrieval_hit(self) -> bool:
        return bool(set(self.relevant_ids) & set(self.retrieved_ids))

    @property
    def packed_hit(self) -> bool:
        return bool(set(self.relevant_ids) & set(self.packed_ids))

    @property
    def packed_first_hit_rank(self) -> int | None:
        relevant = set(self.relevant_ids)
        for index, item_id in enumerate(self.packed_ids, start=1):
            if item_id in relevant:
                return index
        return None

    @property
    def packed_recall(self) -> float:
        if not self.relevant_ids:
            return 0.0
        return len(set(self.relevant_ids) & set(self.packed_ids)) / len(set(self.relevant_ids))

    @property
    def false_positive(self) -> bool:
        return self.expect_empty and bool(self.packed_ids)


@dataclass(frozen=True)
class PackedContextEvalReport:
    positive_queries: int
    retrieval_hit_rate: float
    packed_hit_rate: float
    packed_mrr: float
    mean_packed_recall: float
    negative_queries: int
    negative_false_positives: int


def evaluate_packed_context(results: list[PackedContextCaseResult]) -> PackedContextEvalReport:
    positives = [r for r in results if not r.expect_empty and r.relevant_ids]
    negatives = [r for r in results if r.expect_empty]

    if positives:
        retrieval_hit_rate = sum(1 for r in positives if r.retrieval_hit) / len(positives)
        packed_hit_rate = sum(1 for r in positives if r.packed_hit) / len(positives)
        packed_mrr = sum(
            0.0 if r.packed_first_hit_rank is None else 1.0 / r.packed_first_hit_rank
            for r in positives
        ) / len(positives)
        mean_packed_recall = sum(r.packed_recall for r in positives) / len(positives)
    else:
        retrieval_hit_rate = 0.0
        packed_hit_rate = 0.0
        packed_mrr = 0.0
        mean_packed_recall = 0.0

    return PackedContextEvalReport(
        positive_queries=len(positives),
        retrieval_hit_rate=retrieval_hit_rate,
        packed_hit_rate=packed_hit_rate,
        packed_mrr=packed_mrr,
        mean_packed_recall=mean_packed_recall,
        negative_queries=len(negatives),
        negative_false_positives=sum(1 for r in negatives if r.false_positive),
    )
