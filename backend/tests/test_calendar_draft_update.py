from app.routers.memory_review import _calendar_structured_value, _is_end_after_start


def test_calendar_structured_value_all_day():
    value = _calendar_structured_value(
        title="Meeting GH Risk",
        event_date="2026-05-22",
    )

    assert value == "Meeting GH Risk | due_date=2026-05-22"


def test_calendar_structured_value_timed():
    value = _calendar_structured_value(
        title="Meeting GH Risk",
        event_date="2026-05-22",
        start_at="2026-05-22T15:00:00+07:00",
        end_at="2026-05-22T16:00:00+07:00",
    )

    assert "due_date=2026-05-22" in value
    assert "start_at=2026-05-22T15:00:00+07:00" in value
    assert "end_at=2026-05-22T16:00:00+07:00" in value


def test_end_after_start_validation():
    assert _is_end_after_start(
        "2026-05-22T15:00:00+07:00",
        "2026-05-22T16:00:00+07:00",
    ) is True
    assert _is_end_after_start(
        "2026-05-22T16:00:00+07:00",
        "2026-05-22T15:00:00+07:00",
    ) is False
