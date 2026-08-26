import pytest

from app.services.calendar_candidate_extractor import (
    has_calendar_signal,
    is_public_situational_update,
)


@pytest.mark.parametrize(
    "message",
    [
        "hari ini di Jakarta katanya akan ada demo di DPR",
        "besok katanya ada macet di Sudirman",
        "nanti ada konser di GBK",
    ],
)
def test_public_situational_updates_do_not_trigger_calendar_signal(message):
    assert is_public_situational_update(message) is True
    assert has_calendar_signal(message) is False


def test_explicit_reminder_about_public_situation_still_triggers_calendar_signal():
    message = "ingatkan aku hari ini jam 3 kalau ada demo di DPR"

    assert is_public_situational_update(message) is False
    assert has_calendar_signal(message) is True


def test_product_demo_schedule_is_not_treated_as_public_demo_news():
    message = "jadwalkan demo produk besok jam 2"

    assert is_public_situational_update(message) is False
    assert has_calendar_signal(message) is True
