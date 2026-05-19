from app.services.background_extraction_gate import decide


def test_casual_chat_runs_no_heavy_extractors():
    decision = decide(
        user_message="halo apa kabar?",
        assistant_response="baik, ada yang bisa dibantu?",
        recent_messages=[],
    )

    assert decision.run_legacy_memory is False
    assert decision.run_memory_intelligence is False
    assert decision.run_goal_intelligence is False
    assert decision.run_mood_memory_feedback is False


def test_explicit_memory_signal_runs_memory_intelligence_only():
    decision = decide(
        user_message="ingat ya, panggil aku Syahid",
        assistant_response="siap",
        recent_messages=[],
    )

    assert decision.run_legacy_memory is False
    assert decision.run_memory_intelligence is True
    assert decision.run_goal_intelligence is False


def test_goal_signal_runs_goal_intelligence():
    decision = decide(
        user_message="aku pengen lebih konsisten olahraga tahun ini",
        assistant_response="itu bisa jadi goal yang bagus",
        recent_messages=[],
    )

    assert decision.run_goal_intelligence is True


def test_short_answer_to_identity_question_runs_memory_intelligence():
    decision = decide(
        user_message="7 Januari hehe",
        assistant_response="noted",
        recent_messages=[
            {"role": "assistant", "content": "Kapan ulang tahunmu?"},
        ],
    )

    assert decision.run_memory_intelligence is True


def test_debugging_frustration_runs_mood_feedback():
    decision = decide(
        user_message="ini error deploy bikin pusing, kasih command langsung",
        assistant_response="cd project && flyctl deploy",
        recent_messages=[],
    )

    assert decision.run_mood_memory_feedback is True
