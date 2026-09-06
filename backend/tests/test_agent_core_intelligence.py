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



async def test_agent_core_draft_uses_supported_anthropic_kwargs(
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    captured = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)

            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text=(
                            '{"should_create":true,'
                            '"title":"Prepare roadmap",'
                            '"desired_outcome":"Produce a demo-ready roadmap",'
                            '"priority":"normal",'
                            '"steps":['
                            '{"title":"Define scope",'
                            '"description":null,'
                            '"step_kind":"internal",'
                            '"requires_verification":false},'
                            '{"title":"Verify roadmap",'
                            '"description":null,'
                            '"step_kind":"verify",'
                            '"requires_verification":true}'
                            ']}'
                        )
                    )
                ]
            )

    fake_client = SimpleNamespace(
        messages=FakeMessages()
    )

    monkeypatch.setattr(
        agent_core_intelligence,
        "get_claude",
        lambda: fake_client,
    )

    draft = await (
        agent_core_intelligence
        ._draft_objective(
            user_message=(
                "Tolong buat objective untuk "
                "menyiapkan roadmap demo."
            )
        )
    )

    assert draft.should_create is True
    assert draft.title == "Prepare roadmap"

    assert (
        captured["model"]
        == agent_core_intelligence.settings.UTILITY_LLM_MODEL
    )
    assert captured["max_tokens"] == 1_400
    assert (
        captured["system"]
        == agent_core_intelligence.OBJECTIVE_DRAFT_PROMPT
    )

    assert "temperature" not in captured

    assert captured["messages"] == [
        {
            "role": "user",
            "content": (
                "Tolong buat objective untuk "
                "menyiapkan roadmap demo."
            ),
        }
    ]
