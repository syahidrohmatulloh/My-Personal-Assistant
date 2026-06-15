from app.services import calendar_confirmation_actions as actions


def test_batal_yang_2_targets_second_pending_for_dismiss():
    decision = actions._deterministic_confirmation_decision(
        user_message="batal yang 2",
        suggestions=[{"id": "pending-1"}, {"id": "pending-2"}],
    )

    assert decision is not None
    assert decision.action == "dismiss"
    assert decision.target_memory_id == "pending-2"
    assert decision.reason == "deterministic_indexed_reply"


def test_masukin_yang_1_targets_first_pending_for_local_accept():
    decision = actions._deterministic_confirmation_decision(
        user_message="masukin yang 1",
        suggestions=[{"id": "pending-1"}, {"id": "pending-2"}],
    )

    assert decision is not None
    assert decision.action == "accept_local"
    assert decision.target_memory_id == "pending-1"
    assert decision.reason == "deterministic_indexed_reply"


def test_sync_yang_1_ke_google_targets_first_pending_for_google_accept():
    decision = actions._deterministic_confirmation_decision(
        user_message="sync yang 1 ke google calendar",
        suggestions=[{"id": "pending-1"}, {"id": "pending-2"}],
    )

    assert decision is not None
    assert decision.action == "accept_google"
    assert decision.target_memory_id == "pending-1"
    assert decision.reason == "deterministic_indexed_reply"


def test_ordinal_words_are_supported():
    decision = actions._deterministic_confirmation_decision(
        user_message="batal yang kedua",
        suggestions=[{"id": "pending-1"}, {"id": "pending-2"}],
    )

    assert decision is not None
    assert decision.action == "dismiss"
    assert decision.target_memory_id == "pending-2"


def test_indexed_action_is_not_slot_fill():
    assert not actions._looks_like_pending_detail_update("batal yang 2")
    assert not actions._looks_like_pending_detail_update("masukin yang 1")
    assert not actions._looks_like_pending_detail_update("sync yang 1 ke google")
