from datetime import datetime

from app.services import chat_time_helpers


def test_parse_client_local_time_accepts_browser_local_time() -> None:
    now, timezone = chat_time_helpers.parse_client_local_time(
        {"local_time": "2026-08-23 09:07:00", "timezone": "Asia/Jakarta"}
    )

    assert now == datetime(2026, 8, 23, 9, 7, 0)
    assert timezone == "Asia/Jakarta"


def test_parse_client_local_time_handles_missing_or_invalid_context() -> None:
    assert chat_time_helpers.parse_client_local_time(None) == (None, None)

    now, timezone = chat_time_helpers.parse_client_local_time(
        {"local_time": "not-a-time", "timezone": "Asia/Jakarta"}
    )

    assert now is None
    assert timezone == "Asia/Jakarta"


def test_interpret_hour_with_period_handles_indonesian_dayparts() -> None:
    now = datetime(2026, 8, 23, 15, 0, 0)

    assert chat_time_helpers.interpret_hour_with_period(5, None, now) == 17
    assert chat_time_helpers.interpret_hour_with_period(1, "siang", now) == 13
    assert chat_time_helpers.interpret_hour_with_period(7, "malam", now) == 19
    assert chat_time_helpers.interpret_hour_with_period(12, "malam", now) == 0


def test_extract_mentioned_times_calculates_remaining_time() -> None:
    now = datetime(2026, 8, 23, 9, 7, 0)

    items = chat_time_helpers.extract_mentioned_times("meeting jam 1 siang", now)

    assert items
    assert items[0]["phrase"] == "jam 1 siang"
    assert items[0]["interpreted_time"] == "2026-08-23 13:00"
    assert items[0]["minutes_remaining"] == 233
    assert items[0]["remaining"] == "3 jam 53 menit"


def test_render_time_sensitive_calculation_block_requires_time_signal_and_client_time() -> None:
    assert chat_time_helpers.render_time_sensitive_calculation_block(
        "halo beb",
        {"local_time": "2026-08-23 09:07:00", "timezone": "Asia/Jakarta"},
    ) is None

    assert chat_time_helpers.render_time_sensitive_calculation_block(
        "meeting jam 1 siang",
        {},
    ) is None


def test_render_time_sensitive_calculation_block_includes_deterministic_context() -> None:
    text = chat_time_helpers.render_time_sensitive_calculation_block(
        "meeting jam 1 siang",
        {"local_time": "2026-08-23 09:07:00", "timezone": "Asia/Jakarta"},
    )

    assert text is not None
    assert "Deterministic local-time calculation" in text
    assert "Browser local time now: 2026-08-23 09:07:00 (Asia/Jakarta)" in text
    assert "jam 1 siang" in text
    assert "2026-08-23 13:00" in text
    assert "3 jam 53 menit" in text
