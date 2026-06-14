from app.services import calendar_conflicts


def _event(
    *,
    event_id: str,
    title: str,
    start: str,
    end: str,
    google_id: str | None = None,
):
    return {
        "id": event_id,
        "calendar_event_title": title,
        "calendar_event_start_at": start,
        "calendar_event_end_at": end,
        "calendar_event_all_day": False,
        "google_calendar_event_id": google_id,
        "_record_source": "google" if google_id else "local",
    }


def test_detects_timed_calendar_overlap():
    result = calendar_conflicts.detect_calendar_conflicts(
        proposed_record=_event(
            event_id="new",
            title="New Meeting",
            start="2026-06-14T17:00:00+07:00",
            end="2026-06-14T17:30:00+07:00",
        ),
        candidate_records=[
            _event(
                event_id="existing",
                title="Existing Meeting",
                start="2026-06-14T17:15:00+07:00",
                end="2026-06-14T17:45:00+07:00",
            )
        ],
    )

    assert result["has_conflicts"] is True
    assert result["conflicts"][0]["title"] == "Existing Meeting"


def test_adjacent_events_do_not_conflict():
    result = calendar_conflicts.detect_calendar_conflicts(
        proposed_record=_event(
            event_id="new",
            title="New Meeting",
            start="2026-06-14T17:00:00+07:00",
            end="2026-06-14T17:30:00+07:00",
        ),
        candidate_records=[
            _event(
                event_id="next",
                title="Next Meeting",
                start="2026-06-14T17:30:00+07:00",
                end="2026-06-14T18:00:00+07:00",
            )
        ],
    )

    assert result["has_conflicts"] is False


def test_ignores_all_day_and_target_event():
    proposed = _event(
        event_id="target",
        title="Target",
        start="2026-06-14T17:00:00+07:00",
        end="2026-06-14T17:30:00+07:00",
        google_id="google-target",
    )

    all_day = {
        "id": "all-day",
        "calendar_event_title": "All day",
        "calendar_event_all_day": True,
        "calendar_event_start_at": "2026-06-14T00:00:00+07:00",
        "calendar_event_end_at": "2026-06-15T00:00:00+07:00",
    }

    result = calendar_conflicts.detect_calendar_conflicts(
        proposed_record=proposed,
        candidate_records=[proposed, all_day],
        exclude_ids={"target"},
        exclude_google_event_ids={"google-target"},
    )

    assert result["has_conflicts"] is False
