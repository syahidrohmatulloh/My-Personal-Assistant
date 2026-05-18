from app.services.interaction_preferences import render_interaction_preferences_block


def test_render_returns_none_for_empty_rows():
    assert render_interaction_preferences_block([]) is None


def test_render_filters_non_interaction_memories():
    block = render_interaction_preferences_block(
        [
            {
                "content": "User likes coffee",
                "structured_field": "coffee",
                "confidence": 0.99,
                "superseded": False,
            }
        ]
    )

    assert block is None


def test_render_interaction_preferences_block():
    block = render_interaction_preferences_block(
        [
            {
                "content": "User prefers careful comprehensive fixes instead of incremental guessing.",
                "structured_field": "aliyya_coding_support_style",
                "confidence": 0.86,
                "superseded": False,
            },
            {
                "content": "User appreciates polished theme-aware UI.",
                "structured_field": "ui_design_taste",
                "confidence": 0.82,
                "superseded": False,
            },
            {
                "content": "Old preference",
                "structured_field": "aliyya_relationship_style",
                "confidence": 0.9,
                "superseded": True,
            },
        ]
    )

    assert block is not None
    assert "## ALIYYA INTERACTION PREFERENCES" in block
    assert "not user mood and not companion mood" in block
    assert "aliyya_coding_support_style" in block
    assert "ui_design_taste" in block
    assert "Old preference" not in block
    assert "Do not recite these preferences" in block


def test_render_truncates_long_content():
    block = render_interaction_preferences_block(
        [
            {
                "content": "x" * 500,
                "structured_field": "aliyya_relationship_style",
                "confidence": 0.9,
                "superseded": False,
            }
        ]
    )

    assert block is not None
    assert len(block) < 600
    assert "…" in block
