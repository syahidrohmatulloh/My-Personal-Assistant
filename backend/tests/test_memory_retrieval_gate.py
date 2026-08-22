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


def test_self_regulation_terms_are_personal_memory_cues() -> None:
    from app.services.memory_retrieval_gate import should_retrieve_memory

    for query in ["jangan overthinking", "lagi cemas", "burnout banget"]:
        decision = should_retrieve_memory(query)
        assert decision.should_retrieve is True
        assert decision.reason == "personal_cue:self_regulation"


def test_rank_memory_rows_supports_personal_relaxed_threshold() -> None:
    from app.services import memory

    rows = [
        {
            "id": "mem-low",
            "content": "User wants to be reminded to rest when overthinking",
            "kind": "preference",
            "category": "preferences",
            "similarity": 0.4277,
            "confidence": 0.9,
            "status": "active",
            "archived": False,
            "superseded": False,
        }
    ]

    assert memory.rank_memory_rows(rows) == []

    relaxed = memory.rank_memory_rows(
        rows,
        min_similarity=memory.PERSONAL_CUE_MIN_SIMILARITY,
    )
    assert [row["id"] for row in relaxed] == ["mem-low"]


def test_retrieve_relevant_recovers_personal_near_miss_with_relaxed_threshold(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    from app.services import memory

    async def fake_embed_query(_query: str):
        return [0.1, 0.2, 0.3]

    class FakeRpc:
        def execute(self):
            return SimpleNamespace(
                data=[
                    {
                        "id": "mem-low",
                        "content": "User wants to be reminded to rest when overthinking",
                        "kind": "preference",
                        "category": "preferences",
                        "similarity": 0.4277,
                        "confidence": 0.9,
                        "status": "active",
                        "archived": False,
                        "superseded": False,
                    }
                ]
            )

    class FakeSupabase:
        def rpc(self, *_args, **_kwargs):
            return FakeRpc()

    monkeypatch.setattr(memory, "embed_query", fake_embed_query)
    monkeypatch.setattr(memory, "get_supabase", lambda: FakeSupabase())

    rows = asyncio.run(
        memory.retrieve_relevant(
            "user-123",
            "jangan overthinking",
            limit=10,
        )
    )

    assert [row["id"] for row in rows] == ["mem-low"]


def test_retrieve_relevant_still_blocks_public_current_queries(monkeypatch) -> None:
    import asyncio

    from app.services import memory

    async def fail_embed_query(_query: str):
        raise AssertionError("embed_query should not run for public/current queries")

    monkeypatch.setattr(memory, "embed_query", fail_embed_query)

    rows = asyncio.run(
        memory.retrieve_relevant(
            "user-123",
            "berapa harga saham hari ini",
            limit=10,
        )
    )

    assert rows == []

