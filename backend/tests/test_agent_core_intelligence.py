from app.services import agent_core_intelligence


def test_explicit_objective_request_is_detected() -> None:
    assert (
        agent_core_intelligence
        .is_explicit_objective_activation_request(
            "Tolong buat objective untuk menyiapkan lender meeting ini."
        )
    )

    assert (
        agent_core_intelligence
        .is_explicit_objective_activation_request(
            "Track this as an objective sampai deliverable selesai."
        )
    )


def test_plain_goal_language_is_not_agent_objective() -> None:
    assert not (
        agent_core_intelligence
        .is_explicit_objective_activation_request(
            "Aku punya goal untuk lebih sehat tahun ini."
        )
    )


def test_capability_question_does_not_create_objective() -> None:
    capability_only_messages = (
        "Can you create objectives?",
        "Can you create an objective?",
        "Can you create an objective",
        "Can you track this as an objective?",
        "Bisa nggak kamu buat objective?",
        "Bisa nggak kamu buat objective",
        "Bisakah kamu buatkan objektif?",
        "Apa kamu bisa track ini sebagai objective?",
    )

    for message in capability_only_messages:
        assert not (
            agent_core_intelligence
            .is_explicit_objective_activation_request(
                message
            )
        )


def test_capability_wording_with_explicit_override_can_activate() -> None:
    explicit_messages = (
        (
            "Bisa nggak kamu buat objective ini sekarang? "
            "Tolong buat objective untuk menyiapkan lender meeting."
        ),
        (
            "Can you please create an objective for preparing "
            "the lender meeting now?"
        ),
    )

    for message in explicit_messages:
        assert (
            agent_core_intelligence
            .is_explicit_objective_activation_request(
                message
            )
        )


def test_objective_mention_without_creation_action_is_not_enough() -> None:
    assert not (
        agent_core_intelligence
        .is_explicit_objective_activation_request(
            "Objective ini sebenarnya maksudnya apa?"
        )
    )


def test_agent_core_uses_configured_utility_model() -> None:
    from pathlib import Path

    source = Path(
        "app/services/agent_core_intelligence.py"
    ).read_text(encoding="utf-8")

    assert "model=settings.UTILITY_LLM_MODEL" in source
    assert 'model="claude-haiku-4-5"' not in source
