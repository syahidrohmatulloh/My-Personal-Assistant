"""Smoke tests for memory_intelligence service.

Tests focus on the decision logic (threshold gating, source priority, structured
field handling). External calls (Haiku, embeddings, Supabase) are mocked.

Run:
    cd backend && uv run python tests/test_memory_intelligence.py
or:
    cd backend && uv run pytest tests/test_memory_intelligence.py -v
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Allow running directly without pytest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import memory_intelligence as mi
from app.services.memory_intelligence import CandidateMemory


# ---------------------------------------------------------------------------
# Helpers — fake Haiku that returns predetermined candidate JSON
# ---------------------------------------------------------------------------


def _mock_haiku_response(candidates: list[dict]):
    """Build a mock anthropic response object."""
    import json
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(candidates)
    response = MagicMock()
    response.content = [text_block]
    return response


def _stub_extract_pipeline(
    fake_candidates: list[dict],
    *,
    existing_matches: list[dict] | None = None,
    existing_identity: dict | None = None,
):
    """Context manager set of patches for the full pipeline.

    Returns a dict of mocks we can inspect after the call:
      - insert_mock: captures memories.insert() rows
      - update_mock: captures memories.update() rows (supersede / bump)
      - identity_upsert_mock: captures user_identity upserts
    """
    # === Mock Claude (Haiku) ===
    claude_mock = MagicMock()
    claude_mock.messages.create = AsyncMock(
        return_value=_mock_haiku_response(fake_candidates)
    )

    # === Mock embedder ===
    embed_mock = AsyncMock(return_value=[0.0] * 1024)

    # === Mock Supabase ===
    insert_capture: list[list[dict]] = []
    update_capture: list[dict] = []
    identity_upsert_capture: list[dict] = []

    def fake_supabase():
        sb = MagicMock()

        # Table chain — flexible chainable mock
        def table(name: str):
            t = MagicMock()
            t._table_name = name

            # memories.insert()
            def insert(row):
                ins = MagicMock()
                ins.execute = MagicMock(
                    return_value=MagicMock(data=[{"id": f"new-{len(insert_capture)}"}])
                )
                insert_capture.append(row if isinstance(row, list) else [row])
                return ins

            # memories.update().eq().execute() chain
            class UpdateChain:
                def __init__(self, payload):
                    self.payload = payload
                    self._eq_args: list[tuple] = []

                def eq(self, k, v):
                    self._eq_args.append((k, v))
                    return self

                def execute(self):
                    update_capture.append({
                        "table": name, "payload": self.payload,
                        "where": self._eq_args,
                    })
                    return MagicMock(data=[])

            def update(payload):
                return UpdateChain(payload)

            # select chain for various reads
            class SelectChain:
                def __init__(self):
                    self._eq_args = []
                    self._ilike = None
                    self._limit = None
                    self._order = None

                def eq(self, k, v):
                    self._eq_args.append((k, v))
                    return self

                def ilike(self, k, v):
                    self._ilike = (k, v)
                    return self

                def limit(self, n):
                    self._limit = n
                    return self

                def order(self, *args, **kwargs):
                    self._order = (args, kwargs)
                    return self

                def maybe_single(self):
                    return self

                def execute(self):
                    # user_identity read
                    if name == "user_identity":
                        return MagicMock(data=existing_identity)
                    # memories supersede lookup — return seeded matches if any
                    # selector args present (eq on user_id + structured_field /
                    # superseded, OR ilike on content).
                    if name == "memories" and (self._ilike or self._eq_args):
                        rows = existing_matches or []
                        selected_id = None
                        for k, v in self._eq_args:
                            if k == "id":
                                selected_id = v
                                break
                        if selected_id is not None:
                            rows = [r for r in rows if r.get("id") == selected_id]
                        return MagicMock(data=rows)
                    return MagicMock(data=[])

            def select(*args, **kwargs):
                return SelectChain()

            # upsert (for user_identity)
            def upsert(payload, on_conflict=None):
                up = MagicMock()
                up.execute = MagicMock(return_value=MagicMock(data=[payload]))
                if name == "user_identity":
                    identity_upsert_capture.append(payload)
                return up

            t.insert = insert
            t.update = update
            t.select = select
            t.upsert = upsert
            return t

        sb.table = table

        # rpc (cosine match)
        rpc_mock = MagicMock()
        rpc_mock.execute = MagicMock(return_value=MagicMock(data=existing_matches or []))
        sb.rpc = MagicMock(return_value=rpc_mock)
        return sb

    return {
        "patches": [
            patch("app.services.memory_intelligence.get_claude", return_value=claude_mock),
            patch("app.services.memory_intelligence.embed_document", embed_mock),
            patch("app.services.memory_intelligence.get_supabase", side_effect=fake_supabase),
            # safe_execute just calls the function with a fresh fake supabase.
            patch(
                "app.services.memory_intelligence.safe_execute",
                side_effect=lambda fn: fn(fake_supabase()),
            ),
        ],
        "insert_capture": insert_capture,
        "update_capture": update_capture,
        "identity_upsert_capture": identity_upsert_capture,
    }


# ---------------------------------------------------------------------------
# Test 1: birthday short answer after assistant question
# ---------------------------------------------------------------------------


def test_birthday_short_answer_saved_with_structured_field():
    """Assistant: 'kapan ulang tahunmu?' → User: '7 Januari hehe'
    Should save with structured_field=birthday and write to user_identity.
    """
    fake = [{
        "content": "User's birthday is January 7",
        "category": "important_dates",
        "source_priority": "user_answer_in_context",
        "confidence": 0.88,
        "evidence": ["7 Januari hehe"],
        "structured_field": "birthday",
        "structured_value": "7 Januari",
        "is_correction": False,
    }]
    setup = _stub_extract_pipeline(fake, existing_identity={"profile": {"birthday": "1995-01-07"}})
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1",
            conversation_id="c1",
            recent_messages=[
                {"role": "assistant", "content": "kapan ulang tahunmu?"},
                {"role": "user", "content": "7 Januari hehe"},
            ],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result["saved"] == 1, result
    # Birthday should be inserted as memory.
    assert any(
        "birthday" in r[0].get("content", "").lower()
        for r in setup["insert_capture"]
    ), setup["insert_capture"]
    # NEW: insert row must persist structured_field + structured_value.
    inserted = setup["insert_capture"][0][0]
    assert inserted.get("structured_field") == "birthday", inserted
    assert inserted.get("structured_value") == "1995-01-07", inserted
    # AND structured profile field should be canonical if an upsert is needed.
    # If profile already has the same ISO birthday, _upsert_identity_field is
    # correctly a no-op to avoid unnecessary profile rewrites.
    if setup["identity_upsert_capture"]:
        profile = setup["identity_upsert_capture"][0]["profile"]
        assert profile.get("birthday") == "1995-01-07", profile


# ---------------------------------------------------------------------------
# Test 2: user correction supersedes old memory
# ---------------------------------------------------------------------------


def test_correction_supersedes_old_memory():
    """User: 'actually my birthday is 8 January, not 7' → correct old, save new."""
    fake = [{
        "content": "User's birthday is January 8",
        "category": "important_dates",
        "source_priority": "user_correction",
        "confidence": 0.92,
        "evidence": ["actually my birthday is 8 January"],
        "structured_field": "birthday",
        "structured_value": "8 Januari",
        "is_correction": True,
    }]
    # Old memory exists.
    existing = [{
        "id": "old-mem-1",
        "content": "User's birthday is January 7",
        "category": "important_dates",
        "similarity": 0.95,
        "embedding": [0.0] * 1024,
        "structured_field": "birthday",
        "structured_value": "1995-01-07",
    }]
    setup = _stub_extract_pipeline(
        fake,
        existing_matches=existing,
        existing_identity={"profile": {"birthday": "1995-01-07"}},
    )
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1",
            conversation_id="c1",
            recent_messages=[
                {"role": "user", "content": "actually my birthday is 8 January, not 7"},
            ],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result["saved"] == 1
    assert result["superseded"] == 1, result
    # The old memory should have an update with superseded=true.
    supersede_updates = [u for u in setup["update_capture"] if u["payload"].get("superseded") is True]
    assert supersede_updates, setup["update_capture"]
    # Identity profile should now show new value.
    assert setup["identity_upsert_capture"]
    assert setup["identity_upsert_capture"][0]["profile"]["birthday"] == "1995-01-08"


# ---------------------------------------------------------------------------
# Test 3: assistant_confirmation alone is not enough
# ---------------------------------------------------------------------------


def test_assistant_confirmation_alone_does_not_save():
    """Assistant said something, user only said 'ok'. Should NOT save with high confidence."""
    fake = [{
        "content": "User lives in Bandung",
        "category": "identity",
        "source_priority": "assistant_confirmation",
        "confidence": 0.7,   # decent but should be blocked by source guard
        "evidence": ["ok"],
        "structured_field": None,
        "structured_value": None,
        "is_correction": False,
    }]
    setup = _stub_extract_pipeline(fake, existing_identity={"profile": {"birthday": "1995-01-07"}})
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1",
            conversation_id="c1",
            recent_messages=[
                {"role": "assistant", "content": "Sepertinya kamu di Bandung kan?"},
                {"role": "user", "content": "ok"},
            ],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result["saved"] == 0
    assert result["skipped"] >= 1
    # And no memory inserted.
    assert not setup["insert_capture"]


# ---------------------------------------------------------------------------
# Test 4: random date not saved as birthday without context
# ---------------------------------------------------------------------------


def test_random_date_not_saved_as_birthday():
    """User mentioned a date in passing. Haiku might try to mark structured_field=birthday
    with weak source. Service should drop it."""
    fake = [{
        "content": "User mentioned January 7",
        "category": "important_dates",
        # Notice: source is NOT explicit_user_statement or user_answer_in_context.
        # This simulates Haiku being optimistic but missing the question context.
        "source_priority": "repeated_pattern",
        "confidence": 0.75,
        "evidence": ["I'll see you on January 7"],
        "structured_field": "birthday",   # incorrectly flagged
        "structured_value": "7 Januari",
        "is_correction": False,
    }]
    setup = _stub_extract_pipeline(fake, existing_identity={"profile": {}})
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1",
            conversation_id="c1",
            recent_messages=[
                {"role": "user", "content": "we should meet on January 7"},
            ],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result["saved"] == 0, result
    assert not setup["insert_capture"]
    # And identity profile NOT touched.
    assert not setup["identity_upsert_capture"]


# ---------------------------------------------------------------------------
# Test 5 (bonus): low-confidence answer skipped
# ---------------------------------------------------------------------------


def test_low_confidence_skipped():
    fake = [{
        "content": "User likes coffee",
        "category": "preferences",
        "source_priority": "user_answer_in_context",
        "confidence": 0.50,   # below 0.75 threshold for this source
        "evidence": ["maybe coffee idk"],
        "structured_field": None,
        "structured_value": None,
        "is_correction": False,
    }]
    setup = _stub_extract_pipeline(fake)
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1", conversation_id="c1",
            recent_messages=[
                {"role": "assistant", "content": "kamu prefer kopi atau teh?"},
                {"role": "user", "content": "maybe coffee idk"},
            ],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result["saved"] == 0
    assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# Test 6: explicit user statement clearly saved
# ---------------------------------------------------------------------------


def test_explicit_user_statement_saved():
    fake = [{
        "content": "User works as a software engineer",
        "category": "identity",
        "source_priority": "explicit_user_statement",
        "confidence": 0.95,
        "evidence": ["I'm a software engineer"],
        "structured_field": None,
        "structured_value": None,
        "is_correction": False,
    }]
    setup = _stub_extract_pipeline(fake)
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1", conversation_id="c1",
            recent_messages=[
                {"role": "user", "content": "I'm a software engineer btw"},
            ],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result["saved"] == 1, result


# ---------------------------------------------------------------------------
# Test 7: empty candidate list (Haiku returned nothing)
# ---------------------------------------------------------------------------


def test_empty_candidates_no_op():
    setup = _stub_extract_pipeline([])
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1", conversation_id="c1",
            recent_messages=[{"role": "user", "content": "hi"}],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result == {"candidates": 0, "saved": 0, "skipped": 0, "superseded": 0}


# ---------------------------------------------------------------------------
# Test 8: empty messages no-op
# ---------------------------------------------------------------------------


def test_empty_messages_no_op():
    result = asyncio.run(mi.extract_and_persist(
        user_id="u1", conversation_id="c1", recent_messages=[],
    ))
    assert result == {"candidates": 0, "saved": 0, "skipped": 0, "superseded": 0}


# ---------------------------------------------------------------------------
# Test 9: category → kind mapping is sane
# ---------------------------------------------------------------------------


def test_category_to_legacy_kind_mapping():
    assert mi._category_to_legacy_kind("identity") == "fact"
    assert mi._category_to_legacy_kind("preferences") == "preference"
    assert mi._category_to_legacy_kind("goals") == "plan"
    assert mi._category_to_legacy_kind("routines") == "context"
    assert mi._category_to_legacy_kind("important_dates") == "fact"
    assert mi._category_to_legacy_kind("nonexistent") == "fact"


# ---------------------------------------------------------------------------
# Test 10: dedupe candidates by content
# ---------------------------------------------------------------------------


def test_dedupe_candidates_drops_identical():
    cands = [
        CandidateMemory(
            content="User likes coffee",
            category="preferences",
            source_priority="explicit_user_statement",
            confidence=0.9,
        ),
        CandidateMemory(
            content="USER LIKES COFFEE",  # same content, different case
            category="preferences",
            source_priority="explicit_user_statement",
            confidence=0.85,
        ),
    ]
    out = mi._dedupe_candidates(cands)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# Test 11: structured supersede uses eq on structured_field (deterministic)
# ---------------------------------------------------------------------------


def test_structured_supersede_uses_field_equality():
    """When correcting birthday, old row should be found via structured_field eq,
    NOT via ILIKE on content. This is the deterministic path.

    We seed an old memory categorized as `important_dates` (not `identity`) —
    the previous ILIKE-on-identity approach would have missed it.
    """
    fake = [{
        "content": "User's birthday is 8 January",
        "category": "important_dates",
        "source_priority": "user_correction",
        "confidence": 0.92,
        "evidence": ["actually 8 jan"],
        "structured_field": "birthday",
        "structured_value": "8 Januari",
        "is_correction": True,
    }]
    # Old row is filed under important_dates with structured_field='birthday'.
    # Deterministic supersede should find it via eq('structured_field', 'birthday')
    # regardless of category.
    existing = [{
        "id": "old-bday",
        "content": "User's birthday is 7 January",
        "category": "important_dates",
        "structured_field": "birthday",
        "structured_value": "1995-01-07",
    }]
    setup = _stub_extract_pipeline(
        fake,
        existing_matches=existing,
        existing_identity={"profile": {"birthday": "1995-01-07"}},
    )
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1", conversation_id="c1",
            recent_messages=[
                {"role": "user", "content": "ulangtahunku 8 jan deh bukan 7"},
            ],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result["saved"] == 1
    assert result["superseded"] == 1, result
    # Verify the supersede update happened (old row marked superseded).
    supersede_updates = [u for u in setup["update_capture"] if u["payload"].get("superseded") is True]
    assert supersede_updates, "old row must be superseded"




# ---------------------------------------------------------------------------
# Test 12: birthday normalization and same-value structured dedupe
# ---------------------------------------------------------------------------


def test_birthday_value_normalizes_using_existing_year():
    assert mi._normalize_birthday_value(
        "17 Januari",
        existing_birthday="1995-01-07",
    ) == "1995-01-17"
    assert mi._normalize_birthday_value(
        "January 8",
        existing_birthday="1995-01-07",
    ) == "1995-01-08"
    assert mi._normalize_birthday_value(
        "7 January 1995",
        existing_birthday=None,
    ) == "1995-01-07"
    assert mi._normalize_birthday_value(
        "1995-01-07",
        existing_birthday=None,
    ) == "1995-01-07"
    assert mi._normalize_birthday_value(
        "17 Januari",
        existing_birthday=None,
    ) is None


def test_same_structured_birthday_value_bumps_without_insert():
    fake = [{
        "content": "User's birthday is January 7",
        "category": "important_dates",
        "source_priority": "user_correction",
        "confidence": 0.92,
        "evidence": ["actually still 7 January"],
        "structured_field": "birthday",
        "structured_value": "7 Januari",
        "is_correction": True,
    }]
    existing = [{
        "id": "old-bday",
        "content": "User's birthday is 1995-01-07",
        "category": "important_dates",
        "structured_field": "birthday",
        "structured_value": "1995-01-07",
    }]
    setup = _stub_extract_pipeline(
        fake,
        existing_matches=existing,
        existing_identity={"profile": {"birthday": "1995-01-07"}},
    )
    for p in setup["patches"]: p.start()
    try:
        result = asyncio.run(mi.extract_and_persist(
            user_id="u1", conversation_id="c1",
            recent_messages=[
                {"role": "user", "content": "actually still 7 January"},
            ],
        ))
    finally:
        for p in setup["patches"]: p.stop()

    assert result["saved"] == 0, result
    assert result["superseded"] == 0, result
    assert setup["insert_capture"] == []
    bump_updates = [u for u in setup["update_capture"] if "last_confirmed_at" in u["payload"]]
    assert bump_updates, setup["update_capture"]


# ---------------------------------------------------------------------------
# Inline runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    failed: list[str] = []
    passed = 0
    for name, obj in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(obj):
            try:
                obj()
                print(f"  PASS  {name}")
                passed += 1
            except Exception as exc:
                import traceback
                print(f"  FAIL  {name}: {exc}")
                traceback.print_exc()
                failed.append(name)
    print(f"\n{passed} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)
