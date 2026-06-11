from app.routers.memory_review import _event_title_from_candidate


def test_explicit_calendar_event_title_is_canonical():
    row = {
        "calendar_event_title": "Golf dengan Indosat",
        "structured_value": (
            "Calendar event: Kasih tau kamu hari Minggu agenda golf "
            "di Rainbow Hills dengan Indosat; date 2026-06-14"
        ),
        "content": (
            "User has a scheduled event: Kasih tau kamu hari Minggu "
            "agenda golf di Rainbow Hills dengan Indosat on 2026-06-14"
        ),
    }

    assert _event_title_from_candidate(row) == "Golf dengan Indosat"


def test_human_structured_title_is_used_when_explicit_title_is_missing():
    row = {
        "calendar_event_title": None,
        "structured_value": (
            "Calendar event: Golf dengan Indosat; date 2026-06-14; "
            "starts 2026-06-14T05:52:00+07:00; location Rainbow Hills"
        ),
        "content": "Long original user sentence",
    }

    assert _event_title_from_candidate(row) == "Golf dengan Indosat"


def test_reminder_content_cannot_override_explicit_event_title():
    row = {
        "calendar_event_title": "Golf dengan Indosat",
        "structured_value": "Golf dengan Indosat | due_date=2026-06-14",
        "content": "User wants a reminder: Sabtu malam jam 21.00",
    }

    assert _event_title_from_candidate(row) == "Golf dengan Indosat"
