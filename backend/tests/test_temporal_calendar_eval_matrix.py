import pytest

from app.services.temporal_calendar_policy import assess_calendar_semantics


@pytest.mark.parametrize(
    "message",
    [
        "besok hujan jam 4",
        "katanya besok ada demo di Sudirman",
        "konser Coldplay tanggal 5",
        "Apple launching tanggal 10",
        "meeting mereka kapan?",
        "jam berapa filmnya?",
        "kapan meeting Pak Budi?",
        "enaknya dinner jam berapa besok?",
        "aku biasanya gym jam 6 pagi",
        "setiap Sabtu golf pagi",
        "weekly review tiap Jumat",
        "mungkin besok aku golf",
        "rencananya Jumat dinner sama teman",
        "kalau sempat besok aku ke Bandung",
        "meeting Jumat batal",
        "nggak jadi meeting besok",
        "besok aku di rumah",
        "lusa kayaknya istirahat",
        "tanggal 10 ada konser",
        "Pak Andi ada rapat besok",
        "mereka ada call Jumat",
    ],
)
def test_temporal_but_not_calendar_matrix(message):
    assert assess_calendar_semantics(message).route == "normal_chat"


@pytest.mark.parametrize(
    "message",
    [
        "meeting sama Pak Andi besok jam 10",
        "rapat tim Selasa pagi",
        "Jumat flight GA402 jam 07.20",
        "besok jam 10 appointment dokter",
        "Sabtu jam 7 golf",
        "dinner Jumat jam 19.00",
        "interview Senin jam 09.00",
        "presentasi ke direksi Kamis pagi",
        "workshop Rabu jam 13.00",
    ],
)
def test_committed_personal_event_matrix(message):
    assessment = assess_calendar_semantics(message)
    assert assessment.route == "calendar_candidate"
    assert assessment.eventhood == "event"
    assert assessment.commitment == "committed"


@pytest.mark.parametrize(
    "message",
    [
        "jadwalkan meeting Pak Andi Selasa jam 10",
        "masukkan rapat besok jam 9 ke Calendar",
        "add flight GA402 Friday 07.20 to calendar",
        "tolong ingatkan aku besok jam 7 telepon dokter",
        "buat reminder Jumat jam 5 bayar tagihan",
    ],
)
def test_explicit_calendar_action_matrix(message):
    assessment = assess_calendar_semantics(message)
    assert assessment.route == "calendar_action"
    assert assessment.action_confidence >= 0.95
