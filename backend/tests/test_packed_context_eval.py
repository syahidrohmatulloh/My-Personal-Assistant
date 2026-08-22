from app.services.packed_context_eval import PackedContextCaseResult, evaluate_packed_context


def test_packed_context_eval_reports_hits_and_mrr() -> None:
    report = evaluate_packed_context(
        [
            PackedContextCaseResult(
                query="jangan overthinking",
                relevant_ids=("mem-a",),
                retrieved_ids=("mem-b", "mem-a"),
                packed_ids=("mem-a", "mem-b"),
            ),
            PackedContextCaseResult(
                query="siapa nama anakku",
                relevant_ids=("mem-c",),
                retrieved_ids=("mem-c",),
                packed_ids=("mem-x", "mem-c"),
            ),
        ]
    )

    assert report.positive_queries == 2
    assert report.retrieval_hit_rate == 1.0
    assert report.packed_hit_rate == 1.0
    assert report.packed_mrr == 0.75


def test_packed_context_eval_detects_negative_false_positive() -> None:
    report = evaluate_packed_context(
        [
            PackedContextCaseResult(
                query="cuaca besok",
                relevant_ids=(),
                retrieved_ids=("mem-a",),
                packed_ids=("mem-a",),
                expect_empty=True,
            )
        ]
    )

    assert report.negative_queries == 1
    assert report.negative_false_positives == 1
