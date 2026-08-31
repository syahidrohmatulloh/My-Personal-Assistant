from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.companion_comeback_affect import (
    COOLDOWN_HOURS,
    MIN_GAP_HOURS,
    build_settings_inspector,
)


NOW = datetime(
    2026,
    9,
    1,
    0,
    0,
    tzinfo=timezone.utc,
)


def _settings(**overrides):
    row = {
        "companion_mode": "partner",
        "assistant_name": "Aliyya",
        "mood_realism": "dynamic",
        "repair_gate_enabled": False,
        "preferences": {
            "assistant_mode": "life_companion",
        },
    }

    row.update(overrides)

    return row


def test_inspector_ready_when_mode_gate_open_and_no_cooldown():
    inspector = build_settings_inspector(
        _settings(),
        "life_companion",
        now=NOW,
    )

    assert inspector["status"] == "ready"
    assert inspector["mode_gate_open"] is True
    assert inspector["cooldown_active"] is False

    assert (
        inspector["minimum_gap_hours"]
        == MIN_GAP_HOURS
    )

    assert (
        inspector["cadence_multiplier"]
        == 2.0
    )

    assert (
        inspector["cooldown_hours"]
        == COOLDOWN_HOURS
    )

    assert inspector["last_used_at"] is None
    assert inspector["last_label"] is None
    assert inspector["cooldown_until"] is None


def test_inspector_disabled_in_chief_of_staff():
    inspector = build_settings_inspector(
        _settings(),
        "chief_of_staff",
        now=NOW,
    )

    assert (
        inspector["status"]
        == "disabled_by_mode"
    )

    assert (
        inspector["mode_gate_open"]
        is False
    )


def test_inspector_disabled_when_not_partner_dynamic():
    inspector = build_settings_inspector(
        _settings(
            companion_mode="friendly",
            mood_realism="stable",
        ),
        "life_companion",
        now=NOW,
    )

    assert (
        inspector["status"]
        == "disabled_by_mode"
    )

    assert (
        inspector["mode_gate_open"]
        is False
    )


def test_inspector_reports_active_cooldown_and_last_label():
    last_used = (
        NOW
        - timedelta(
            days=1
        )
    )

    row = _settings()

    row["preferences"] = {
        "assistant_mode":
            "life_companion",
        "comeback_affect_last_used_at":
            last_used.isoformat(),
        "comeback_affect_last_label":
            "warm_notice",
    }

    inspector = build_settings_inspector(
        row,
        "life_companion",
        now=NOW,
    )

    assert inspector["status"] == "cooldown"
    assert inspector["cooldown_active"] is True

    assert (
        inspector["last_label"]
        == "warm_notice"
    )

    assert (
        inspector["last_used_at"]
        == last_used.isoformat()
    )

    assert (
        inspector["cooldown_until"]
        == (
            last_used
            + timedelta(
                hours=COOLDOWN_HOURS
            )
        ).isoformat()
    )


def test_inspector_expired_cooldown_returns_ready():
    last_used = (
        NOW
        - timedelta(
            days=8
        )
    )

    row = _settings()

    row["preferences"] = {
        "assistant_mode":
            "life_companion",
        "comeback_affect_last_used_at":
            last_used.isoformat(),
        "comeback_affect_last_label":
            "warm_return",
    }

    inspector = build_settings_inspector(
        row,
        "life_companion",
        now=NOW,
    )

    assert inspector["status"] == "ready"
    assert inspector["cooldown_active"] is False


def test_router_contract_exposes_read_only_inspector_without_importing_runtime_config():
    repo_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    router_text = (
        repo_root
        / "backend/app/routers/companion.py"
    ).read_text()

    api_text = (
        repo_root
        / "frontend/lib/api.ts"
    ).read_text()

    page_text = (
        repo_root
        / "frontend/app/settings/companion/page.tsx"
    ).read_text()

    assert "ComebackAffectInspectorOut" in router_text
    assert "comeback_affect:" in router_text
    assert "build_settings_inspector(" in router_text

    assert (
        'Omit<CompanionSettings, "comeback_affect">'
        in api_text
    )

    assert (
        "Warm comeback inspector"
        in page_text
    )
