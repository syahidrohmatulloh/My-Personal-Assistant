from app.services.memory_retrieval_gate import should_retrieve_memory


def test_blocks_obvious_public_current_queries() -> None:
    queries = [
        "berapa harga saham hari ini",
        "siapa presiden amerika sekarang",
        "berapa kurs dollar hari ini",
        "rekomendasi laptop gaming terbaru",
        "cuaca besok di jakarta",
    ]

    for query in queries:
        decision = should_retrieve_memory(query)
        assert decision.should_retrieve is False, query
        assert decision.reason.startswith("public_current:"), query


def test_blocks_low_signal_queries() -> None:
    for query in ["", "halo", "ok", "terima kasih"]:
        decision = should_retrieve_memory(query)
        assert decision.should_retrieve is False


def test_allows_personal_memory_queries() -> None:
    queries = [
        "kamu inget aku suka apa?",
        "kalau aku overthinking",
        "ingatkan aku istirahat",
        "siapa Aghnia buat aku?",
        "jadwalku minggu ini apa?",
        "apa preferensi aku?",
        "self regulation preference",
    ]

    for query in queries:
        decision = should_retrieve_memory(query)
        assert decision.should_retrieve is True, query


def test_personal_cue_overrides_public_current_pattern() -> None:
    queries = [
        "kamu inget kurs dollar yang pernah aku tanya?",
        "rekomendasi laptop sesuai preferensi aku",
        "cuaca yang biasa aku suka waktu liburan apa?",
    ]

    for query in queries:
        decision = should_retrieve_memory(query)
        assert decision.should_retrieve is True, query
        assert decision.reason.startswith("personal_cue:")


def test_default_allows_non_obvious_queries() -> None:
    decision = should_retrieve_memory("tolong bantu susun pesan yang elegan")
    assert decision.should_retrieve is True
    assert decision.reason == "default_allow"


def test_memory_py_calls_retrieval_gate() -> None:
    from pathlib import Path

    text = Path("app/services/memory.py").read_text(encoding="utf-8")
    assert "should_retrieve_memory" in text
