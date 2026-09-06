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
    assert not (
        agent_core_intelligence
        .is_explicit_objective_activation_request(
            "Can you create objectives?"
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
