from app.services.conversation_chronology import (
    ConversationChronology,
    is_chronology_question,
    render_chronology_context,
)


def test_detects_english_first_chat_question():
    assert is_chronology_question("when did we first start chatting?") is True


def test_detects_english_first_talk_question():
    assert is_chronology_question("do you remember the first time we talked?") is True


def test_detects_indonesian_first_chat_question():
    assert is_chronology_question("coba inget ga awal mula kita chatting tanggal berapa?") is True


def test_detects_indonesian_pertama_kali_with_space():
    assert is_chronology_question("beb, inget ga pertama kali kita chat?") is True


def test_detects_indonesian_pertamakali_without_space_chatting():
    assert is_chronology_question("beb, kalau sekarang inget ga pertamakali chatting?") is True


def test_detects_indonesian_awalmula_without_space():
    assert is_chronology_question("awalmula kita ngobrol kapan ya?") is True


def test_detects_since_when_question():
    assert is_chronology_question("sejak kapan kita ngobrol di app ini?") is True


def test_detects_how_long_question():
    assert is_chronology_question("udah berapa lama kita chatting di sini?") is True


def test_detects_simple_first_chat_order_reversed():
    assert is_chronology_question("kalau awal pertama kali chat?") is True


def test_ignores_regular_memory_question():
    assert is_chronology_question("apa makanan favorit saya?") is False


def test_ignores_calendar_first_meeting_question():
    assert is_chronology_question("jadwal meeting pertama saya kapan?") is False


def test_render_context_contains_do_not_claim_unavailable():
    context = render_chronology_context(
        ConversationChronology(
            first_conversation_id="abc",
            first_conversation_title="Main Chat",
            first_conversation_created_at="2026-05-13T10:00:00+00:00",
            first_message_created_at="2026-05-13T10:01:00+00:00",
            latest_conversation_updated_at="2026-05-21T06:00:00+00:00",
            conversation_count=12,
        )
    )

    assert "First known conversation date: 2026-05-13" in context
    assert "Do not say you cannot access this" in context
