from datetime import datetime, timezone

from app.services.proactive_nudges import parse_nudge_from_chat, parse_nudge_request


def test_parse_explicit_indonesian_reminder_time():
    parsed = parse_nudge_request(
        user_message="tolong ingetin aku jam 10.15 buat berangkat",
        client_context={
            "local_time": "2026-06-03T10:03:00+07:00",
            "timezone_offset_minutes": -420,
        },
    )

    assert parsed is not None
    assert parsed.title == "berangkat"
    assert parsed.due_at == datetime(2026, 6, 3, 3, 15, tzinfo=timezone.utc)


def test_parse_confirmation_from_assistant_reminder_offer():
    parsed = parse_nudge_from_chat(
        user_message="oke",
        assistant_response=(
            "Siap beb! Aku akan ingetin kamu di chat ini sekitar jam 10.15, "
            "biar ada waktu siap-siap sebelum berangkat jam 10.30."
        ),
        client_context={
            "local_time": "2026-06-03T10:03:00+07:00",
            "timezone_offset_minutes": -420,
        },
    )

    assert parsed is not None
    assert parsed.title == "berangkat"
    assert parsed.message == "Waktunya kamu berangkat."
    assert parsed.due_at == datetime(2026, 6, 3, 3, 15, tzinfo=timezone.utc)


def test_confirmation_without_reminder_offer_does_not_schedule():
    parsed = parse_nudge_from_chat(
        user_message="oke",
        assistant_response="Oke beb, noted.",
        client_context={
            "local_time": "2026-06-03T10:03:00+07:00",
            "timezone_offset_minutes": -420,
        },
    )

    assert parsed is None


def test_parse_loose_natural_indonesian_reminder_text():
    parsed = parse_nudge_request(
        user_message="beb ingetin lagi ya aku 1 menit lagi buat chat lagi sama kamu",
        client_context={
            "local_time": "2026-06-03T10:03:00+07:00",
            "timezone_offset_minutes": -420,
        },
    )

    assert parsed is not None
    assert parsed.message == "Waktunya kamu chat lagi sama aku."
