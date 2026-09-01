import pytest

from app.services.temporal_calendar_policy import (
    assess_calendar_semantics,
    requires_calendar_handling,
)


@pytest.mark.parametrize(
    ("message", "route", "commitment"),
    [
        ("meeting sama tim marketing besok pagi", "calendar_candidate", "committed"),
        ("Jumat flight GA402 jam 07.20", "calendar_candidate", "committed"),
        ("besok aku ada dokter jam 10", "calendar_candidate", "committed"),
        ("Masukkan flight GA402 Jumat jam 07.20 ke Calendar", "calendar_action", "committed"),
        ("Minggu depan jadwalkan review sama Sarah", "calendar_action", "committed"),
        ("Besok mungkin aku mau golf", "normal_chat", "tentative"),
        ("Besok kayaknya aku mau istirahat di rumah", "normal_chat", "tentative"),
        ("Aku biasanya golf Sabtu pagi", "normal_chat", "none"),
        ("Besok katanya hujan jam 4", "normal_chat", "none"),
        ("Apple launching tanggal 10 September", "normal_chat", "none"),
        ("Jam berapa enaknya dinner besok?", "normal_chat", "none"),
        ("Pak Budi ada meeting besok", "normal_chat", "none"),
        ("Meeting Jumat batal", "normal_chat", "cancelled"),
        ("Besok aku mau ke Bandung", "normal_chat", "none"),
    ],
)
def test_calendar_semantic_routes(message, route, commitment):
    assessment = assess_calendar_semantics(message)
    assert assessment.route == route
    assert assessment.commitment == commitment
    assert requires_calendar_handling(assessment) is (
        route in {"calendar_candidate", "calendar_action", "clarify_eventhood"}
    )


def test_time_certainty_is_separate_from_action_certainty():
    assessment = assess_calendar_semantics("Besok katanya hujan jam 4")
    assert assessment.temporal_confidence >= 0.9
    assert assessment.action_confidence <= 0.05
    assert assessment.route == "normal_chat"


def test_explicit_reminder_is_action_not_ambient_schedule():
    assessment = assess_calendar_semantics(
        "tolong ingatkan aku besok jam 7 telepon dokter"
    )
    assert assessment.route == "calendar_action"
    assert assessment.persistence_target == "reminder"
    assert assessment.action_confidence == 1.0


def test_conditional_self_regulation_reminder_is_not_schedule():
    assessment = assess_calendar_semantics(
        "kalau aku overthinking tolong ingetin aku istirahat"
    )
    assert assessment.route == "normal_chat"
    assert "calendar.self_regulation_not_schedule" in assessment.reason_codes

@pytest.mark.parametrize(
    "message",
    [
        "engga ada meeting sama direksi besok",
        "enggak ada meeting sama direksi besok",
        "nggak ada meeting besok",
        "ngga ada rapat besok",
        "gak ada jadwal besok",
        "ga ada agenda besok",
        "tidak ada appointment besok",
        "belum ada meeting besok",
        "aku tidak punya meeting besok",
        "saya ga punya jadwal besok",
        "jadwal aku besok kosong",
        "agenda besok kosong",
        "no meeting tomorrow",
        "there is no meeting tomorrow",
        "there's no meeting tomorrow",
        "i don't have a meeting tomorrow",
        "i have no meeting tomorrow",
    ],
)
def test_negated_or_absent_event_never_routes_to_calendar(
    message,
):
    assessment = assess_calendar_semantics(
        message
    )

    assert assessment.route == "normal_chat"
    assert assessment.action_confidence == 0.0
    assert (
        "calendar.absence_statement_not_schedule"
        in assessment.reason_codes
    )
    assert (
        requires_calendar_handling(
            assessment
        )
        is False
    )


@pytest.mark.parametrize(
    "message",
    [
        (
            "nggak ada masalah, meeting sama direksi "
            "besok jam 10 tetap jadi"
        ),
        (
            "aku nggak mau telat meeting sama direksi "
            "besok jam 10"
        ),
    ],
)
def test_negative_words_not_tied_to_event_absence_remain_schedulable(
    message,
):
    assessment = assess_calendar_semantics(
        message
    )

    assert assessment.route == "calendar_candidate"
