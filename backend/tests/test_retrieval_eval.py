from app.services.retrieval_eval import (
    QueryResult,
    evaluate,
    first_hit_rank,
    mean_similarity_of_hits,
    recall_at_k,
    reciprocal_rank,
)


def test_first_hit_rank() -> None:
    assert first_hit_rank(["x", "a", "b"], {"a"}) == 2
    assert first_hit_rank(["x", "y"], {"a"}) is None


def test_recall_at_k_basic() -> None:
    retrieved = ["a", "b", "c", "d", "e", "f"]
    relevant = {"c", "f"}
    assert recall_at_k(retrieved, relevant, 5) == 0.5
    assert recall_at_k(retrieved, relevant, 10) == 1.0


def test_recall_at_k_edges() -> None:
    assert recall_at_k([], set(), 5) == 1.0
    assert recall_at_k(["a"], {"a"}, 0) == 0.0
    assert recall_at_k([], {"a"}, 5) == 0.0


def test_reciprocal_rank() -> None:
    assert reciprocal_rank(["x", "a", "b"], {"a"}) == 0.5
    assert reciprocal_rank(["a", "b"], {"a"}) == 1.0
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0


def test_mean_similarity_of_hits() -> None:
    result = QueryResult("q", ["a", "b", "c"], {"a", "c"}, [0.9, 0.2, 0.7])
    assert mean_similarity_of_hits(result) == (0.9 + 0.7) / 2

    no_scores = QueryResult("q", ["a"], {"a"}, None)
    assert mean_similarity_of_hits(no_scores) is None


def test_evaluate_aggregate() -> None:
    results = [
        QueryResult("q1", ["a", "b", "c"], {"a"}, [0.9, 0.5, 0.4]),
        QueryResult("q2", ["x", "y", "z"], {"z"}, [0.8, 0.6, 0.55]),
        QueryResult("q3", ["m", "n"], {"absent"}, [0.7, 0.6]),
    ]

    report = evaluate(results)

    assert report.n_queries == 3
    assert abs(report.mrr - (1.0 + 1 / 3 + 0.0) / 3) < 1e-9
    assert abs(report.recall_at_5 - (1.0 + 1.0 + 0.0) / 3) < 1e-9
    assert abs(report.recall_at_10 - (1.0 + 1.0 + 0.0) / 3) < 1e-9
    assert abs(report.hit_rate - 2 / 3) < 1e-9
    assert report.mean_first_hit_rank == 2.0


def test_evaluate_empty() -> None:
    report = evaluate([])
    assert report.n_queries == 0
    assert report.recall_at_5 == 0.0
    assert report.recall_at_10 == 0.0
    assert report.mrr == 0.0
    assert report.hit_rate == 0.0
    assert report.mean_first_hit_rank is None
    assert report.mean_hit_similarity is None


def test_report_lines_render_na_safely() -> None:
    report = evaluate([QueryResult("q", ["a"], {"a"}, None)])
    lines = "\n".join(report.as_lines())
    assert "recall@5" in lines
    assert "mean hit similarity: n/a" in lines
