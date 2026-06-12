from pathlib import Path


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_calendar_action_executes_before_prompt_and_stream():
    action_index = CHAT.index(
        "await calendar_draft_actions.apply_chat_calendar_draft_action("
    )
    prompt_index = CHAT.index(
        "# === Build prompt with cached base + volatile context ==="
    )
    response_index = CHAT.index(
        "return StreamingResponse(",
        prompt_index,
    )

    assert action_index < prompt_index < response_index


def test_authoritative_result_is_added_to_volatile_context():
    assert (
        "calendar_draft_actions.render_calendar_action_result_context("
        in CHAT
    )
    assert (
        "The Calendar action has already been attempted before this reply"
        in CHAT
    )
    assert "Say the action succeeded only when success is true" in CHAT


def test_calendar_action_is_not_scheduled_twice_in_background():
    assert (
        "calendar_draft_actions.apply_chat_calendar_draft_action,"
        not in CHAT
    )
    assert (
        CHAT.count(
            "calendar_draft_actions.apply_chat_calendar_draft_action("
        )
        == 1
    )


def test_stream_receives_explicit_calendar_action_state():
    assert "calendar_action_turn: bool = False" in CHAT
    assert "calendar_action_snapshot_dirty: bool = False" in CHAT
    assert (
        "calendar_action_turn=is_calendar_draft_action_turn"
        in CHAT
    )
    assert (
        "calendar_action_snapshot_dirty=calendar_action_snapshot_dirty"
        in CHAT
    )



def test_failed_action_does_not_mark_snapshot_dirty_by_default():
    start = CHAT.index("calendar_snapshot_dirty = bool(")
    dirty_block = CHAT[start:start + 500]

    assert "calendar_action_snapshot_dirty" in dirty_block
    assert "should_create_google_calendar_event" in dirty_block
    assert "should_extract_calendar_candidate" in dirty_block
    assert "should_apply_calendar_draft_action" not in dirty_block

    assert "calendar_action_success" in CHAT
    assert '"local_update_after_google_patch_failed"' in CHAT
    assert '"local_archive_after_google_delete_failed"' in CHAT

def test_action_turn_skips_pending_confirmation_router():
    assert "if not calendar_action_turn:" in CHAT
    assert (
        "calendar_confirmation_actions.apply_calendar_confirmation_decision"
        in CHAT
    )
