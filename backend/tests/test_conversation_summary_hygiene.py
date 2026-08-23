import inspect

from app.services import conversation_summary


def test_summarize_conversation_does_not_log_summary_content() -> None:
    source = inspect.getsource(conversation_summary.summarize_conversation)

    assert "summary='%s'" not in source
    assert "summary[:80]" not in source
    assert "summary_chars=%d" in source


def test_summary_retrieval_uses_gate_before_embedding() -> None:
    source = inspect.getsource(conversation_summary.retrieve_related_summaries)

    assert "should_retrieve_memory(query_text)" in source
    assert source.index("should_retrieve_memory(query_text)") < source.index("embed_query(query_text)")
    assert "summary retrieval trace:" in source



def test_summary_retrieval_uses_production_visible_logger() -> None:
    source = inspect.getsource(conversation_summary.retrieve_related_summaries)

    assert "production_log.info" in source
    assert "summary retrieval gate:" in source
    assert "summary retrieval trace:" in source



def test_summary_retrieval_uses_dynamic_episode_threshold() -> None:
    source = inspect.getsource(conversation_summary.retrieve_related_summaries)

    assert "classify_episode_text(query_text)" in source
    assert "effective_min_similarity" in source
    assert "EPISODIC_SUMMARY_MIN_SIMILARITY" in source
    assert '"p_min_similarity": effective_min_similarity' in source



def test_summary_retrieval_trace_includes_elapsed_ms_and_safe_rpc_error() -> None:
    source = inspect.getsource(conversation_summary.retrieve_related_summaries)

    assert "elapsed_ms=%.1f" in source
    assert "time.perf_counter()" in source
    assert "summary retrieval rpc failed:" in source
    assert "type(exc).__name__" in source
