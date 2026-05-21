from app.services.memory_supersession import (
    decide_supersession,
    is_single_value_field,
)


def test_sleep_pattern_is_single_value():
    assert is_single_value_field("sleep_pattern") is True


def test_food_preference_is_multi_value():
    assert is_single_value_field("food_preference") is False


def test_visual_memory_is_multi_value():
    assert is_single_value_field("visual_memory_personal_photo") is False


def test_scheduled_event_is_multi_value():
    assert is_single_value_field("scheduled_event") is False


def test_decides_to_supersede_changed_single_value():
    decision = decide_supersession("often_stays_up_late", "sleeps_regularly")
    assert decision.should_supersede is True


def test_does_not_supersede_same_value():
    decision = decide_supersession("GMT+7", "gmt+7")
    assert decision.should_supersede is False


def test_does_not_supersede_near_duplicate_value():
    decision = decide_supersession("prefers concise answers", "prefers concise answer")
    assert decision.should_supersede is False
