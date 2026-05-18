from app.services.user_mood_prompt import render_user_mood_block


def test_user_mood_prompt_returns_none_without_signal():
    assert render_user_mood_block(None) is None
    assert render_user_mood_block({"has_data": False}) is None


def test_user_mood_prompt_is_compact_and_separates_companion_mood():
    block = render_user_mood_block(
        {
            "has_data": True,
            "latest": {"mood": -2, "energy": -3, "stress": 4},
            "baseline": {"mood": 0.2, "energy": -0.1, "stress": 1.0},
            "delta": {
                "mood": -2.2,
                "energy": -2.9,
                "stress": 3.0,
                "label_mood": "lower than usual",
                "label_energy": "lower than usual",
                "label_stress": "higher than usual",
            },
            "causal": ["workload", "debugging issue", "late night"],
            "evidence": [
                "2026-05-18: User wrote a very long journal note about feeling overloaded because of backend errors and deployment issues.",
                "extra evidence should still be short",
                "third evidence",
                "fourth evidence should not render",
            ],
            "confidence": 0.74,
            "sample_size": 8,
            "current_message_signal": {
                "mood_hint": "frustrated",
                "matched_keywords": ["error", "failed"],
            },
        }
    )

    assert block is not None
    assert "## USER MOOD CONTEXT" in block
    assert "USER's inferred state, not Aliyya's companion mood" in block
    assert "Latest self-report" in block
    assert "30-day baseline" in block
    assert "Baseline delta" in block
    assert "Confidence: 0.74" in block
    assert "fourth evidence should not render" not in block
    assert "changing companion mood" in block


def test_user_mood_prompt_does_not_render_raw_verbatim_journal_header():
    block = render_user_mood_block(
        {
            "has_data": True,
            "evidence": ["This is a private note that should be trimmed and framed carefully."],
            "confidence": 0.5,
        }
    )

    assert block is not None
    assert "Evidence (verbatim from journal)" not in block
    assert "Supporting signals, summarized/trimmed" in block


def test_user_mood_prompt_handles_current_message_only():
    block = render_user_mood_block(
        {
            "has_data": True,
            "current_message_signal": {
                "mood_hint": "stressed",
                "matched_keywords": ["capek", "pusing"],
            },
        }
    )

    assert block is not None
    assert "Current message hint: stressed" in block
    assert "Keyword-only" in block
