import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.services import memory
from app.services import memory_lifecycle_governance
from app.services import metacognitive_policy


MIGRATION = Path(
    "schema_phase420_m35c1_safe_retrieval_governance.sql"
)


class _RpcResult:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeSupabase:
    def __init__(self, rows):
        self.rows = rows

    def rpc(self, name, args):
        assert name == "match_memories"
        assert args["p_match_count"] >= 1
        return _RpcResult(self.rows)


def _active_row(**overrides):
    row = {
        "id": "active",
        "content": "User prefers concise commands",
        "kind": "preference",
        "source": "auto",
        "source_conversation_id": None,
        "created_at": "2026-09-03T00:00:00+00:00",
        "similarity": 0.92,
        "category": "preferences",
        "confidence": 0.90,
        "structured_field": "communication_style",
        "structured_value": "concise commands",
        "superseded": False,
        "source_priority": "explicit_user_statement",
        "status": "active",
        "archived": False,
        "deleted_at": None,
    }
    row.update(overrides)
    return row


def test_rpc_migration_filters_every_canonical_hidden_state():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "coalesce(m.superseded, false) = false" in sql
    assert "coalesce(m.archived, false) = false" in sql
    assert "m.deleted_at is null" in sql

    assert "'archived'" in sql
    assert "'superseded'" in sql
    assert "'deleted'" in sql


def test_rpc_projects_governance_metadata_but_not_confirmation_timestamp():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    returns_block = sql.split(
        "returns table (",
        1,
    )[1].split(
        ")\nlanguage sql",
        1,
    )[0]

    assert "source_priority text" in returns_block
    assert "status text" in returns_block
    assert "archived boolean" in returns_block
    assert "deleted_at timestamptz" in returns_block

    # Historical confirmation timestamps are intentionally quarantined until
    # M35c2 historical repair.
    assert "last_confirmed_at" not in returns_block


def test_python_defense_in_depth_still_rejects_hidden_rows():
    rows = [
        _active_row(id="archived-flag", archived=True),
        _active_row(
            id="archived-status",
            status="archived",
        ),
        _active_row(
            id="superseded-flag",
            superseded=True,
        ),
        _active_row(
            id="superseded-status",
            status="superseded",
        ),
        _active_row(
            id="deleted-at",
            deleted_at="2026-09-03T00:00:00+00:00",
        ),
        _active_row(
            id="deleted-status",
            status="deleted",
        ),
        _active_row(id="active"),
    ]

    ranked = memory.rank_memory_rows(
        rows,
        min_similarity=0.50,
    )

    assert [row["id"] for row in ranked] == ["active"]


def test_projected_historical_provenance_does_not_gain_rank_authority():
    assert memory.SOURCE_PRIORITY_RANKING_ENABLED is False

    base = _active_row(
        id="base",
        category="other",
        structured_field=None,
        structured_value=None,
        confidence=0.95,
        similarity=0.82,
    )

    explicit = {
        **base,
        "id": "explicit",
        "source_priority": "explicit_user_statement",
    }
    repeated = {
        **base,
        "id": "repeated",
        "source_priority": "repeated_pattern",
    }

    assert (
        memory.memory_retrieval_score(explicit)
        == memory.memory_retrieval_score(repeated)
    )


def test_rpc_provenance_survives_into_python_and_inference_stays_unverified(
    monkeypatch,
):
    async def fake_embed_query(_text):
        return [0.1, 0.2]

    rpc_row = _active_row(
        id="system-inference",
        source_priority="system_inference",
        confidence=0.54,
        similarity=0.93,
    )

    monkeypatch.setattr(
        memory,
        "embed_query",
        fake_embed_query,
    )
    monkeypatch.setattr(
        memory,
        "get_supabase",
        lambda: _FakeSupabase([rpc_row]),
    )

    rows = asyncio.run(
        memory.retrieve_relevant(
            "user-123456",
            "ingatkan aku istirahat",
            limit=8,
        )
    )

    assert len(rows) == 1

    row = rows[0]

    assert row["source_priority"] == "system_inference"
    assert row["status"] == "active"
    assert row["archived"] is False
    assert row["deleted_at"] is None

    # M35c1 deliberately keeps historical confirmation timestamps out of
    # the retrieval projection.
    assert "last_confirmed_at" not in row

    lifecycle = (
        memory_lifecycle_governance
        .assess_memory_lifecycle(row)
    )
    assert lifecycle.needs_confirmation is True
    assert lifecycle.confirmed is False

    trust, refs = metacognitive_policy._assess_evidence(
        [row],
        now=datetime.now(timezone.utc),
    )

    assert trust == "unverified"
    assert refs == ("system-inference",)
