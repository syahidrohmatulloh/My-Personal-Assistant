from app.services import memory


def test_build_retrieval_diagnostics_reports_safe_metadata_only() -> None:
    text = memory.build_retrieval_diagnostics(
        [
            {
                "content": "User's private preference should not leak",
                "category": "preferences",
                "structured_field": "assistant_name",
                "structured_value": "Hana",
                "retrieval_score": 1.2345,
                "similarity": 0.91,
            },
            {
                "content": "User's private location should not leak",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
                "retrieval_score": 0.834,
            },
        ],
        [
            {
                "title": "Sensitive project title",
                "summary": "Sensitive summary should not leak",
                "similarity": 0.75,
            }
        ],
    )

    assert "memories=2" in text
    assert "summaries=1" in text
    assert "categories=identity,preferences" in text
    assert "fields=assistant_name,timezone" in text
    assert "avg_memory_score=1.034" in text
    assert "max_memory_score=1.234" in text
    assert "avg_summary_score=0.750" in text

    assert "private preference" not in text
    assert "private location" not in text
    assert "Hana" not in text
    assert "Asia/Jakarta" not in text
    assert "Sensitive project title" not in text
    assert "Sensitive summary" not in text


def test_build_retrieval_diagnostics_handles_empty_context() -> None:
    text = memory.build_retrieval_diagnostics([], [])

    assert text == (
        "memory_context:"
        " memories=0"
        " summaries=0"
        " categories=-"
        " fields=-"
        " avg_memory_score=-"
        " max_memory_score=-"
        " avg_summary_score=-"
    )
