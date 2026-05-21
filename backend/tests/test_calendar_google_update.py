from app.routers.memory_review import _build_google_calendar_event_payload


def test_synced_event_update_uses_same_payload_builder_for_timed_event():
    payload = _build_google_calendar_event_payload(
        title="Updated Meeting GH Risk",
        event_date="2026-05-22",
        description="Updated from Aliyya",
        start_at="2026-05-22T15:30:00+07:00",
        end_at="2026-05-22T16:30:00+07:00",
    )

    assert payload["summary"] == "Updated Meeting GH Risk"
    assert payload["start"] == {"dateTime": "2026-05-22T15:30:00+07:00"}
    assert payload["end"] == {"dateTime": "2026-05-22T16:30:00+07:00"}


def test_synced_event_update_payload_can_fall_back_to_all_day():
    payload = _build_google_calendar_event_payload(
        title="Updated all-day event",
        event_date="2026-05-22",
        description="Updated from Aliyya",
        start_at=None,
        end_at=None,
    )

    assert payload["start"] == {"date": "2026-05-22"}
    assert payload["end"] == {"date": "2026-05-23"}
