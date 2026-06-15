from app.services import calendar_confirmation_actions as actions


def test_short_location_reply_updates_generic_pending_location():
    row = {
        "id": "pending-1",
        "calendar_event_title": "Nonton bioskop sama Aghnia",
        "calendar_event_date": "2026-06-16",
        "calendar_event_start_at": "2026-06-16T12:00:00+07:00",
        "calendar_event_end_at": "2026-06-16T13:00:00+07:00",
        "calendar_event_location": "bioskop",
    }

    updates = actions._extract_pending_detail_updates("CGV Agora", row)

    assert updates["calendar_event_location"] == "CGV Agora"


def test_explicit_location_reply_updates_pending_location():
    row = {
        "id": "pending-1",
        "calendar_event_title": "Fisioterapi",
        "calendar_event_date": "2026-06-22",
        "calendar_event_location": None,
    }

    updates = actions._extract_pending_detail_updates("lokasinya di WM Center Kebayoran", row)

    assert updates["calendar_event_location"] == "WM Center Kebayoran"


def test_time_range_reply_updates_pending_time():
    row = {
        "id": "pending-1",
        "calendar_event_title": "Fisioterapi",
        "calendar_event_date": "2026-06-22",
        "calendar_event_location": "WM Center Kebayoran",
    }

    updates = actions._extract_pending_detail_updates("jamnya 12.00 - 13.00", row)

    assert updates["calendar_event_start_at"] == "2026-06-22T12:00:00+07:00"
    assert updates["calendar_event_end_at"] == "2026-06-22T13:00:00+07:00"
    assert updates["calendar_event_all_day"] is False


def test_short_confirmation_is_deterministic_for_single_pending():
    decision = actions._deterministic_confirmation_decision(
        user_message="iya",
        suggestions=[{"id": "pending-1"}],
    )

    assert decision is not None
    assert decision.action == "accept_local"
    assert decision.target_memory_id == "pending-1"
    assert decision.confidence == 1.0


def test_short_dismiss_is_deterministic_for_single_pending():
    decision = actions._deterministic_confirmation_decision(
        user_message="gajadi",
        suggestions=[{"id": "pending-1"}],
    )

    assert decision is not None
    assert decision.action == "dismiss"
    assert decision.target_memory_id == "pending-1"
    assert decision.confidence == 1.0


def test_multiple_pending_short_confirmation_asks_clarify():
    decision = actions._deterministic_confirmation_decision(
        user_message="iya",
        suggestions=[{"id": "pending-1"}, {"id": "pending-2"}],
    )

    assert decision is not None
    assert decision.action == "clarify"
    assert decision.target_memory_id is None
    assert decision.reason == "multiple_pending_suggestions"


def test_update_pending_details_receipt_is_multiline_and_asks_confirmation():
    receipt = actions.render_calendar_confirmation_user_receipt(
        {
            "attempted": True,
            "executed": True,
            "action": "update_pending_details",
            "title": "Nonton bioskop sama Aghnia",
            "date": "2026-06-16",
            "start_at": "2026-06-16T12:00:00+07:00",
            "end_at": "2026-06-16T13:00:00+07:00",
            "location": "CGV Agora",
        },
        address_term="beb",
    )

    assert receipt.startswith("Oke, aku update detailnya, beb.")
    assert "\n\nAcara: Nonton bioskop sama Aghnia" in receipt
    assert "Lokasi: CGV Agora" in receipt
    assert receipt.endswith("Mau aku masukin ke Calendar?")
    assert "**Acara:**" not in receipt
