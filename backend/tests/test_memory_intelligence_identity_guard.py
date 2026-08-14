from app.services import memory_intelligence as mi


def test_deterministic_identity_does_not_treat_profession_as_name() -> None:
    candidates = mi._deterministic_identity_candidates(
        "USER: I'm a software engineer btw"
    )

    assert candidates == []


def test_deterministic_identity_still_extracts_explicit_user_name() -> None:
    candidates = mi._deterministic_identity_candidates(
        "USER: my name is Syahid Rohmatulloh"
    )

    assert len(candidates) == 1
    assert candidates[0].structured_field == "name"
    assert candidates[0].structured_value == "Syahid Rohmatulloh"
