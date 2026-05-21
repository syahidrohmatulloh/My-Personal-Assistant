from app.routers.memory_review import _build_google_calendar_event_payload


def test_builds_timed_google_calendar_payload():
    payload = _build_google_calendar_event_payload(
        title="Meeting with GH Risk",
        event_date="2026-05-22",
        description="From Aliyya",
        start_at="2026-05-22T15:00:00+07:00",
        end_at="2026-05-22T16:00:00+07:00",
    )

    assert payload["summary"] == "Meeting with GH Risk"
    assert payload["start"] == {"dateTime": "2026-05-22T15:00:00+07:00"}
    assert payload["end"] == {"dateTime": "2026-05-22T16:00:00+07:00"}


def test_builds_all_day_payload_when_no_time():
    payload = _build_google_calendar_event_payload(
        title="Presentation",
        event_date="2026-05-22",
        description="From Aliyya",
        start_at=None,
        end_at=None,
    )

    assert payload["start"] == {"date": "2026-05-22"}
    assert payload["end"] == {"date": "2026-05-23"}


def test_falls_back_to_all_day_when_datetime_invalid():
    payload = _build_google_calendar_event_payload(
        title="Presentation",
        event_date="2026-05-22",
        description="From Aliyya",
        start_at="not-a-date",
        end_at="also-not-a-date",
    )

    assert payload["start"] == {"date": "2026-05-22"}
    assert payload["end"] == {"date": "2026-05-23"}
