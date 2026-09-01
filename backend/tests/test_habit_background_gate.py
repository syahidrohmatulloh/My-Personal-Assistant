from app.services.background_extraction_gate import decide


def _decision(message: str):
    return decide(
        user_message=message,
        assistant_response="ok",
        recent_messages=[],
    )


def test_explicit_indonesian_routine_runs_memory_intelligence() -> None:
    decision = _decision(
        "Saya biasanya lari pagi setiap Senin"
    )

    assert (
        decision.run_memory_intelligence
        is True
    )


def test_explicit_frequency_runs_memory_intelligence() -> None:
    decision = _decision(
        "Aku gym 3 kali seminggu"
    )

    assert (
        decision.run_memory_intelligence
        is True
    )


def test_explicit_english_routine_runs_memory_intelligence() -> None:
    decision = _decision(
        "I usually read before bed"
    )

    assert (
        decision.run_memory_intelligence
        is True
    )


def test_explicit_habit_correction_runs_memory_intelligence() -> None:
    samples = (
        "Saya berhenti lari pagi",
        "I no longer run",
    )

    for sample in samples:
        assert (
            _decision(
                sample
            ).run_memory_intelligence
            is True
        )


def test_occurrence_report_does_not_need_llm_memory_gate() -> None:
    decision = _decision(
        "Aku baru selesai lari pagi"
    )

    # M32 owns repeated-occurrence learning. A single occurrence should not
    # force memory_intelligence / Haiku to run.
    assert (
        decision.run_memory_intelligence
        is False
    )
