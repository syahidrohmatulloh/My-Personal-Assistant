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


def test_rank_candidates_at_threshold_filters_near_misses() -> None:
    from app.services.retrieval_eval import rank_candidates_at_threshold

    candidates = [
        {"id": "hit", "similarity": 0.42, "retrieval_score": 0.92},
        {"id": "other", "similarity": 0.70, "retrieval_score": 0.50},
    ]

    high = rank_candidates_at_threshold(candidates, threshold=0.50, limit=10)
    low = rank_candidates_at_threshold(candidates, threshold=0.40, limit=10)

    assert [row["id"] for row in high] == ["other"]
    assert [row["id"] for row in low] == ["hit", "other"]


def test_threshold_sweep_recovers_below_threshold_relevant_id() -> None:
    from app.services.retrieval_eval import CandidateCase, threshold_sweep

    cases = [
        CandidateCase(
            query="kalau aku overthinking",
            relevant_ids={"mem1"},
            candidates=[{"id": "mem1", "similarity": 0.42, "retrieval_score": 0.95}],
        )
    ]

    reports = threshold_sweep(cases, [0.50, 0.40], limit=10)

    assert reports[0.50].recall_at_5 == 0.0
    assert reports[0.40].recall_at_5 == 1.0
    assert reports[0.40].mrr == 1.0


def test_diagnose_query_reports_dropped_relevant_candidate() -> None:
    from app.services.retrieval_eval import diagnose_query

    diagnostic = diagnose_query(
        query="kalau aku overthinking",
        relevant_ids={"mem1"},
        production_ids=[],
        unfiltered_candidates=[
            {"id": "mem1", "similarity": 0.42, "retrieval_score": 0.95},
            {"id": "mem2", "similarity": 0.60, "retrieval_score": 0.80},
        ],
        threshold=0.50,
        limit=10,
    )

    assert diagnostic.production_hit is False
    assert diagnostic.first_hit_rank is None
    assert diagnostic.dropped_relevant == [
        {"id": "mem1", "similarity": 0.42, "retrieval_score": 0.95}
    ]
    assert diagnostic.unfiltered_top_ids == ["mem1", "mem2"]


def test_diagnose_query_does_not_report_production_hit_as_dropped() -> None:
    from app.services.retrieval_eval import diagnose_query

    diagnostic = diagnose_query(
        query="overthinking",
        relevant_ids={"mem1"},
        production_ids=["mem1"],
        unfiltered_candidates=[
            {"id": "mem1", "similarity": 0.96, "retrieval_score": 0.99},
        ],
        threshold=0.50,
        limit=10,
    )

    assert diagnostic.production_hit is True
    assert diagnostic.first_hit_rank == 1
    assert diagnostic.dropped_relevant == []


def test_eval_retrieval_rpc_payloads_include_current_supabase_signature() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "eval_retrieval",
        Path(__file__).resolve().parents[1] / "tools" / "eval_retrieval.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    payloads = module._rpc_payloads(
        user_id="user-1",
        embedding=[0.1, 0.2],
        limit=10,
    )

    assert {
        "p_user_id": "user-1",
        "p_query_embedding": [0.1, 0.2],
        "p_match_count": 10,
    } in payloads


def test_load_eval_set_accepts_expect_empty_negative_probe(tmp_path) -> None:
    import importlib.util
    import json
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "eval_retrieval",
        Path(__file__).resolve().parents[1] / "tools" / "eval_retrieval.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps(
            {
                "user_id": "user-123",
                "queries": [
                    {
                        "query": "berapa harga saham hari ini",
                        "relevant_ids": [],
                        "expect_empty": True,
                        "notes": "negative-probe",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    data = module.load_eval_set(path)

    assert data["queries"][0]["expect_empty"] is True


def test_load_eval_set_rejects_expect_empty_with_relevant_ids(tmp_path) -> None:
    import importlib.util
    import json
    from pathlib import Path

    import pytest

    spec = importlib.util.spec_from_file_location(
        "eval_retrieval",
        Path(__file__).resolve().parents[1] / "tools" / "eval_retrieval.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps(
            {
                "user_id": "user-123",
                "queries": [
                    {
                        "query": "bad negative",
                        "relevant_ids": ["id1"],
                        "expect_empty": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expect_empty=true"):
        module.load_eval_set(path)

