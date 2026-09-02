from pathlib import Path


MIGRATION = Path(
    "schema_phase422_m35c2b_historical_confirmation_repair.sql"
)


def _sql():
    return MIGRATION.read_text(
        encoding="utf-8"
    ).lower()


def test_repair_is_frozen_to_pre_m35c2a_corpus():
    sql = _sql()

    assert (
        "2026-09-02 17:40:14+00"
        in sql
    )


def test_repair_has_exact_audited_distribution_guards():
    sql = _sql()

    assert "expected 127" in sql
    assert "expected 106" in sql
    assert "expected 37" in sql
    assert "expected 69" in sql
    assert "expected 21" in sql


def test_phase414_fingerprint_is_exact_utc_minute():
    sql = _sql()

    assert (
        "2026-05-18 07:11:00+00"
        in sql
    )
    assert (
        "2026-05-18 07:12:00+00"
        in sql
    )


def test_insert_default_signature_is_five_seconds():
    sql = _sql()

    assert "extract(" in sql
    assert "last_confirmed_at" in sql
    assert "m.created_at" in sql
    assert ") <= 5" in sql


def test_repair_materializes_exact_candidate_ids_before_update():
    sql = _sql()

    assert (
        "create temporary table "
        "m35c2b_candidate_ids"
        in sql
    )
    assert (
        "insert into m35c2b_candidate_ids"
        in sql
    )

    update_pos = sql.index(
        "update public.memories"
    )
    candidate_pos = sql.index(
        "insert into m35c2b_candidate_ids"
    )

    assert candidate_pos < update_pos


def test_repair_locks_against_concurrent_memory_writes():
    sql = _sql()

    assert (
        "lock table public.memories"
        in sql
    )
    assert (
        "share row exclusive mode"
        in sql
    )


def test_only_confirmation_timestamp_is_updated():
    sql = _sql()

    assert sql.count(
        "update public.memories"
    ) == 1

    assert (
        "set last_confirmed_at = null"
        in sql
    )

    assert "set source_priority" not in sql
    assert "set confidence" not in sql
    assert "set status" not in sql
    assert "set archived" not in sql
    assert "set superseded" not in sql
    assert "set deleted_at" not in sql


def test_no_insert_delete_truncate_on_memories():
    sql = _sql()

    assert (
        "insert into public.memories"
        not in sql
    )
    assert (
        "delete from public.memories"
        not in sql
    )
    assert "truncate public.memories" not in sql


def test_fail_closed_transaction_guards_exist():
    sql = _sql()

    assert sql.lstrip().startswith(
        "--"
    )
    assert "\nbegin;" in sql
    assert "raise exception" in sql
    assert "get diagnostics" in sql
    assert "commit;" in sql


def test_post_repair_preserves_21_ambiguous_timestamps():
    sql = _sql()

    assert (
        "remaining_timestamp_count <> 21"
        in sql
    )
