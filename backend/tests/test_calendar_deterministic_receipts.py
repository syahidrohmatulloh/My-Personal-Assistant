from pathlib import Path

from app.services import calendar_draft_actions


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
SERVICE = Path("app/services/calendar_draft_actions.py").read_text(
    encoding="utf-8"
)


def test_calendar_update_receipt_is_deterministic_and_local_time():
    receipt = calendar_draft_actions.render_calendar_action_user_receipt(
        {
            "attempted": True,
            "success": True,
            "updated": True,
            "deleted": False,
            "action": "update",
            "title": "Dinner sama Aghnia",
            "date": "2026-06-15",
            "start_at": "2026-06-15T12:00:00+00:00",
            "end_at": "2026-06-15T13:00:00+00:00",
            "location": "Epiwalk",
        }
    )

    assert receipt is not None
    assert receipt.startswith("Sudah aku update")
    assert "Acara: Dinner sama Aghnia" in receipt
    assert "Tanggal: 15 Juni 2026" in receipt
    assert "Waktu: 19.00–20.00" in receipt
    assert "Lokasi: Epiwalk" in receipt


def test_calendar_delete_receipt_is_deterministic():
    receipt = calendar_draft_actions.render_calendar_action_user_receipt(
        {
            "attempted": True,
            "success": True,
            "updated": False,
            "deleted": True,
            "action": "delete",
            "title": "Learning Reminder",
        }
    )

    assert receipt is not None
    assert receipt.startswith("Sudah aku hapus")
    assert "Acara: Learning Reminder" in receipt


def test_calendar_conflict_receipt_does_not_claim_update():
    receipt = calendar_draft_actions.render_calendar_action_user_receipt(
        {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": "update",
            "reason": "calendar_conflict_requires_confirmation",
            "title": "Learning Reminder",
            "date": "2026-06-15",
            "start_at": "2026-06-15T11:00:00+00:00",
            "end_at": "2026-06-15T11:30:00+00:00",
            "conflict_analysis": {
                "has_conflicts": True,
                "conflicts": [
                    {
                        "title": "Existing Meeting",
                        "start_at": "2026-06-15T11:15:00+00:00",
                        "end_at": "2026-06-15T11:45:00+00:00",
                    }
                ],
            },
        }
    )

    assert receipt is not None
    assert receipt.startswith("Belum aku update")
    assert "bentrok dengan Existing Meeting pukul 18.15–18.45" in receipt
    assert "Mau tetap lanjut atau pilih jam lain?" in receipt
    assert "Sudah aku update" not in receipt


def test_recurring_scope_receipt_is_deterministic():
    receipt = calendar_draft_actions.render_calendar_action_user_receipt(
        {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": "update",
            "reason": "recurring_scope_required",
        }
    )

    assert receipt is not None
    assert "jadwal berulang" in receipt
    assert "hari ini saja" in receipt
    assert "seluruh rangkaian" in receipt


def test_chat_bypasses_claude_for_calendar_action_receipts():
    assert "calendar_action_receipt =" in CHAT
    assert "render_calendar_action_user_receipt" in CHAT
    assert "if is_calendar_draft_action_turn and calendar_action_receipt:" in CHAT
    assert "_stream_static_assistant_response(" in CHAT
    assert "conversation_id=body.conversation_id" in CHAT
    assert "calendar_snapshot_dirty=calendar_action_snapshot_dirty" in CHAT


def test_static_stream_persists_and_emits_done_for_calendar_receipts():
    assert "conversation_id: str | None = None" in CHAT
    assert "calendar_snapshot_dirty: bool = False" in CHAT
    assert "calendar_snapshot_dirty" in CHAT
    assert "'type': 'done'" in CHAT
    assert "'type': 'done'" in CHAT


def test_service_exposes_user_receipt_renderer():
    assert "def render_calendar_action_user_receipt" in SERVICE
    assert "This is intentionally not LLM-written" in SERVICE


def test_calendar_confirmation_local_receipt_is_multiline():
    from app.services import calendar_confirmation_actions

    receipt = calendar_confirmation_actions.render_calendar_confirmation_user_receipt(
        {
            "attempted": True,
            "executed": True,
            "action": "accept_local",
            "title": "Test Meeting",
            "date": "2026-06-16",
            "start_at": "2026-06-16T03:00:00+00:00",
            "end_at": "2026-06-16T03:30:00+00:00",
            "location": "Zoom",
        }
    )

    assert receipt is not None
    assert receipt.startswith("Sudah aku masukin ke Calendar")
    assert "\n\nAcara: Test Meeting" in receipt
    assert "Tanggal: 16 Juni 2026" in receipt
    assert "Waktu: 10.00–10.30" in receipt
    assert "Lokasi: Zoom" in receipt
    assert "**Acara:**" not in receipt


def test_calendar_confirmation_google_receipt_is_multiline():
    from app.services import calendar_confirmation_actions

    receipt = calendar_confirmation_actions.render_calendar_confirmation_user_receipt(
        {
            "attempted": True,
            "executed": True,
            "action": "accept_google",
            "title": "Test Meeting",
            "date": "2026-06-16",
            "start_at": "2026-06-16T03:00:00+00:00",
            "end_at": "2026-06-16T03:30:00+00:00",
            "location": "Zoom",
            "google_event_id": "google-1",
        }
    )

    assert receipt is not None
    assert receipt.startswith("Sudah aku sync ke Google Calendar")
    assert "\n\nAcara: Test Meeting" in receipt
    assert "Tanggal: 16 Juni 2026" in receipt
    assert "Waktu: 10.00–10.30" in receipt
    assert "Lokasi: Zoom" in receipt
    assert "**Acara:**" not in receipt


def test_direct_google_create_receipt_is_multiline():
    receipt = calendar_draft_actions.render_google_calendar_create_user_receipt(
        {
            "attempted": True,
            "created": True,
            "title": "Test Meeting",
            "date": "2026-06-16",
            "start_at": "2026-06-16T03:00:00+00:00",
            "end_at": "2026-06-16T03:30:00+00:00",
            "location": "Zoom",
            "google_event_id": "google-1",
        }
    )

    assert receipt is not None
    assert receipt.startswith("Sudah aku sync ke Google Calendar")
    assert "\n\nAcara: Test Meeting" in receipt
    assert "Tanggal: 16 Juni 2026" in receipt
    assert "Waktu: 10.00–10.30" in receipt
    assert "Lokasi: Zoom" in receipt
    assert "**Acara:**" not in receipt


def test_chat_bypasses_claude_for_confirmation_and_google_create_receipts():
    assert "render_calendar_confirmation_user_receipt" in CHAT
    assert "apply_calendar_confirmation_decision" in CHAT
    assert "render_google_calendar_create_user_receipt" in CHAT
    assert "create_google_calendar_event_from_chat" in CHAT


def test_calendar_receipts_do_not_hardcode_beb_by_default():
    receipt = calendar_draft_actions.render_calendar_action_user_receipt(
        {
            "attempted": True,
            "success": True,
            "updated": True,
            "deleted": False,
            "action": "update",
            "title": "Dinner sama Aghnia",
            "date": "2026-06-15",
        }
    )

    assert receipt is not None
    assert "beb" not in receipt.casefold()
    assert receipt.startswith("Sudah aku update.")


def test_calendar_receipts_use_dynamic_address_term():
    receipt = calendar_draft_actions.render_calendar_action_user_receipt(
        {
            "attempted": True,
            "success": True,
            "updated": True,
            "deleted": False,
            "action": "update",
            "title": "Dinner sama Aghnia",
            "date": "2026-06-15",
        },
        address_term="Joni",
    )

    assert receipt is not None
    assert receipt.startswith("Sudah aku update, Joni.")
    assert "beb" not in receipt.casefold()


def test_confirmation_receipts_use_dynamic_address_term():
    from app.services import calendar_confirmation_actions

    receipt = calendar_confirmation_actions.render_calendar_confirmation_user_receipt(
        {
            "attempted": True,
            "executed": True,
            "action": "accept_local",
            "title": "Fisioterapi",
            "date": "2026-06-22",
            "start_at": "2026-06-22T05:00:00+00:00",
            "end_at": "2026-06-22T06:00:00+00:00",
            "location": "WM Center Kebayoran",
        },
        address_term="Joni",
    )

    assert receipt is not None
    assert receipt.startswith("Sudah aku masukin ke Calendar, Joni.")
    assert "Waktu: 12.00–13.00" in receipt
    assert "**Acara:**" not in receipt
    assert "beb" not in receipt.casefold()


def test_candidate_preview_is_deterministic_multiline_and_dynamic_address():
    from app.services import calendar_candidate_extractor

    preview = calendar_candidate_extractor.render_calendar_candidate_preview(
        {
            "candidate": True,
            "saved": True,
            "title": "Fisioterapi",
            "date": "2026-06-22",
            "start_at": "2026-06-22T05:00:00+00:00",
            "end_at": "2026-06-22T06:00:00+00:00",
            "location": "WM Center Kebayoran",
        },
        address_term="Joni",
    )

    assert preview is not None
    assert preview.startswith("Joni, ini kayaknya agenda.")
    assert "\n\nAcara: Fisioterapi" in preview
    assert "Tanggal: 22 Juni 2026" in preview
    assert "Waktu: 12.00–13.00" in preview
    assert "Lokasi: WM Center Kebayoran" in preview
    assert "**Acara:**" not in preview
    assert "beb" not in preview.casefold()


def test_chat_has_dynamic_calendar_address_and_candidate_preview_path():
    assert "_load_calendar_address_term" in CHAT
    assert "calendar_address_term" in CHAT
    assert "render_calendar_candidate_preview" in CHAT
    assert "address_term=calendar_address_term" in CHAT


def test_chat_calendar_hard_gate_prevents_claude_preview_fallback():
    assert "_should_hard_gate_calendar_candidate" in CHAT
    assert "calendar_candidate_hard_gate" in CHAT
    assert "_render_calendar_hard_gate_clarification" in CHAT
    assert "deterministic_candidate_preview" in CHAT
    assert "deterministic_calendar_clarification" in CHAT


def test_static_stream_marks_calendar_receipt_source():
    assert "calendar_receipt_source: str | None = None" in CHAT
    assert 'meta_event["calendar_receipt_source"] = calendar_receipt_source' in CHAT


def test_calendar_hard_gate_catches_natural_schedule_messages():
    assert "nonton" in CHAT
    assert "bioskop" in CHAT
    assert "fisioterapi" in CHAT
    assert "has_activity and (has_date or has_time)" in CHAT


def test_calendar_hard_gate_clarification_has_no_markdown_or_hardcoded_beb():
    assert "Bisa sebutkan acara, tanggal, waktu, dan lokasi?" in CHAT
    assert "**Acara:**" not in CHAT
    assert "Beb, ini kayaknya" not in CHAT
