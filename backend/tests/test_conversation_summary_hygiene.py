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
