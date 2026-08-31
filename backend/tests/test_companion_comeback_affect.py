from datetime import datetime, timedelta, timezone

from app.services.companion_comeback_affect import (
    decide_comeback_affect,
    infer_expected_cadence_hours,
    render_prompt_block,
)


def _decision(**overrides):
    base = {
        "gap_hours": 80,
        "expected_cadence_hours": 24,
        "companion_mode": "partner",
        "mood_realism": "dynamic",
        "assistant_mode": "life_companion",
        "user_message": "halo",
        "assistant_name": "Aliyya",
        "user_mood_context": None,
        "cooldown_active": False,
    }

    base.update(overrides)

    return decide_comeback_affect(
        **base
    )


def test_gap_below_minimum_is_suppressed():
    decision = _decision(
        gap_hours=12
    )

    assert (
        decision["label"]
        == "none"
    )

    assert (
        decision["must_suppress_reason"]
        == "gap_below_minimum"
    )


def test_safe_return_after_meaningful_gap():
    decision = _decision(
        gap_hours=80
    )

    assert (
        decision["label"]
        == "warm_return"
    )

    assert (
        decision["expression_policy"]
        == "one_short_warm_line"
    )


def test_named_return_can_be_warm_notice():
    decision = _decision(
        gap_hours=120,
        user_message="halo Aliyya",
    )

    assert (
        decision["label"]
        == "warm_notice"
    )


def test_affectionate_long_return_can_be_warm_lively():
    decision = _decision(
        gap_hours=168,
        user_message="hai beb",
    )

    assert (
        decision["label"]
        == "warm_lively"
    )


def test_serious_work_task_suppresses_total():
    decision = _decision(
        gap_hours=336,
        user_message=
            "tolong draft email ke client",
    )

    assert (
        decision["label"]
        == "none"
    )

    assert (
        decision["must_suppress_reason"]
        == "serious_work_task"
    )


def test_distressed_user_suppresses_total():
    decision = _decision(
        gap_hours=240,
        user_message=
            "aku capek banget hari ini",
        user_mood_context={
            "label": "tired"
        },
    )

    assert (
        decision["label"]
        == "none"
    )

    assert (
        decision["must_suppress_reason"]
        == "user_distressed"
    )


def test_professional_mode_suppresses_total():
    decision = _decision(
        gap_hours=500,
        companion_mode="professional",
    )

    assert (
        decision["label"]
        == "none"
    )

    assert (
        decision["must_suppress_reason"]
        == "mode_not_partner_dynamic"
    )


def test_chief_of_staff_suppresses_total():
    decision = _decision(
        gap_hours=500,
        assistant_mode=
            "chief_of_staff",
    )

    assert (
        decision["label"]
        == "none"
    )

    assert (
        decision["must_suppress_reason"]
        == "assistant_mode_not_life_companion"
    )


def test_cooldown_suppresses_total():
    decision = _decision(
        gap_hours=192,
        cooldown_active=True,
    )

    assert (
        decision["label"]
        == "none"
    )

    assert (
        decision["must_suppress_reason"]
        == "cooldown_active"
    )


def test_apology_never_escalates_beyond_warm_return():
    decision = _decision(
        gap_hours=240,
        user_message=
            "maaf ya beb, baru sempat balik",
    )

    assert (
        decision["label"]
        == "warm_return"
    )


def test_cadence_excludes_current_return_gap():
    now = datetime(
        2026,
        8,
        31,
        tzinfo=timezone.utc,
    )

    timestamps = [
        now,
        now - timedelta(hours=120),
        now - timedelta(hours=144),
        now - timedelta(hours=168),
        now - timedelta(hours=192),
    ]

    assert (
        infer_expected_cadence_hours(
            timestamps
        )
        == 24
    )


def test_prompt_block_forbids_guilt_language():
    block = render_prompt_block(
        _decision(
            gap_hours=80
        )
    )

    assert block
    assert "Never say or imply" in block
    assert "aku ngambek" in block
    assert "kamu ngilang" in block
    assert "aku nungguin kamu" in block


def test_suppressed_decision_has_no_prompt_block():
    block = render_prompt_block(
        _decision(
            gap_hours=12
        )
    )

    assert block is None
