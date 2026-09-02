from app.services.mood_memory_feedback import build_behavioral_memory_candidate


def test_no_candidate_for_general_chat():
    candidate = build_behavioral_memory_candidate(
        user_message="hari ini cuaca bagus ya",
        user_mood_context={"has_data": False},
    )

    assert candidate is None


def test_candidate_for_frustrating_debugging_context():
    candidate = build_behavioral_memory_candidate(
        user_message="pusing banget error deploy flyctl ini bolak-balik gagal, tolong edit command yang bisa langsung saya paste",
        assistant_response="cd /repo/backend\nPYTHONPATH=. uv run pytest tests -q\nflyctl deploy",
        user_mood_context={
            "has_data": True,
            "current_message_signal": {
                "mood_hint": "frustrated",
                "matched_keywords": ["pusing", "gagal"],
            },
        },
    )

    assert candidate is not None
    assert candidate.kind == "preference"
    assert candidate.category == "preferences"
    assert candidate.structured_field == "debugging_support_style_under_frustration"
    assert candidate.structured_value == "paste_ready_commands_root_cause_first_minimal_theory"
    assert candidate.source_priority == "system_inference"
    assert candidate.confidence == 0.54
    assert "paste-ready terminal commands" in candidate.content


def test_payload_shape_is_memory_compatible():
    candidate = build_behavioral_memory_candidate(
        user_message="error pytest gagal terus, kasih command terminal langsung",
        user_mood_context={
            "has_data": True,
            "latest": {"stress": 4, "energy": -3, "mood": -2},
        },
    )

    assert candidate is not None
    payload = candidate.as_memory_payload("user-123")

    assert payload["user_id"] == "user-123"
    assert payload["kind"] == "preference"
    assert payload["category"] == "preferences"
    assert payload["structured_field"] == "debugging_support_style_under_frustration"
    assert payload["source_priority"] == candidate.source_priority
    assert payload["last_confirmed_at"] is None
    assert payload["superseded"] is False
    assert isinstance(payload["evidence"], list)


def test_does_not_create_memory_for_emotion_without_task_context():
    candidate = build_behavioral_memory_candidate(
        user_message="aku lagi capek dan pusing banget hari ini",
        user_mood_context={
            "has_data": True,
            "current_message_signal": {"mood_hint": "tired"},
        },
    )

    assert candidate is None
