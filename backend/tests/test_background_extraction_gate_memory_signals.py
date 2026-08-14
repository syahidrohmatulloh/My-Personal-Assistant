from app.services import background_extraction_gate


def decide(text: str):
    return background_extraction_gate.decide(
        user_message=text,
        assistant_response="",
        recent_messages=[],
        is_first_message=False,
    )


def test_preference_about_phasing_runs_memory_intelligence() -> None:
    decision = decide("H6 nya jangan kebanyakan phase, biar ga mikro progress.")

    assert decision.run_memory_intelligence is True
    assert "memory_signal" in decision.reasons


def test_future_command_constraint_runs_memory_intelligence() -> None:
    decision = decide(
        "Ke depan jangan kasih command npx vercel --prod kecuali saya minta eksplisit."
    )

    assert decision.run_memory_intelligence is True
    assert "memory_signal" in decision.reasons


def test_style_preference_runs_memory_intelligence() -> None:
    decision = decide("Saya lebih suka command yang copy-paste ready dan consulting style.")

    assert decision.run_memory_intelligence is True
    assert "memory_signal" in decision.reasons


def test_generic_done_does_not_run_memory_intelligence() -> None:
    decision = decide("Oke done, sudah sesuai.")

    assert decision.run_memory_intelligence is False


def test_generic_build_status_does_not_run_memory_intelligence() -> None:
    decision = decide("Build sudah pass dan commit sudah push.")

    assert decision.run_memory_intelligence is False
