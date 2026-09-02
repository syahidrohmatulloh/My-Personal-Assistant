-- =============================================================================
-- M35c2b — Historical Confirmation Repair
--
-- Purpose:
--   Remove only historical last_confirmed_at timestamps that are
--   deterministically attributable to:
--
--   B. Phase414 migration-time fingerprint
--   C. legacy insert-time DEFAULT now()
--
-- Frozen pre-M35c2a corpus:
--   created_at < 2026-09-02 17:40:14+00
--
-- Audited distribution:
--   historical rows : 127
--   B candidates     : 37
--   C candidates     : 69
--   repair total     : 106
--   ambiguous keep   : 21
--
-- This migration intentionally does NOT mutate:
--   content
--   evidence
--   source_priority
--   confidence
--   status
--   archived
--   superseded
--   deleted_at
--
-- It changes last_confirmed_at only.
--
-- Fail-closed design:
--   * lock memory writes briefly;
--   * materialize the exact candidate ID set;
--   * assert the audited counts before UPDATE;
--   * UPDATE only those materialized IDs;
--   * assert post-repair counts;
--   * any mismatch raises an exception and rolls the transaction back.
-- =============================================================================

begin;

-- Prevent a concurrent confirmation/write from changing the historical
-- classification between our preflight and UPDATE.
lock table public.memories
    in share row exclusive mode;

create temporary table m35c2b_candidate_ids (
    id uuid primary key,
    repair_class text not null
        check (repair_class in (
            'B_migration_fingerprint',
            'C_insert_default'
        ))
) on commit drop;

insert into m35c2b_candidate_ids (
    id,
    repair_class
)
select
    m.id,
    case
        -- Exact UTC minute previously identified as the Phase414
        -- migration fingerprint.
        when m.last_confirmed_at
                 >= timestamptz '2026-05-18 07:11:00+00'
         and m.last_confirmed_at
                 <  timestamptz '2026-05-18 07:12:00+00'
        then 'B_migration_fingerprint'

        else 'C_insert_default'
    end
from public.memories m
where m.created_at
        < timestamptz '2026-09-02 17:40:14+00'
  and m.last_confirmed_at is not null
  and (
        (
            m.last_confirmed_at
                >= timestamptz '2026-05-18 07:11:00+00'
            and m.last_confirmed_at
                < timestamptz '2026-05-18 07:12:00+00'
        )
        or abs(
            extract(
                epoch from (
                    m.last_confirmed_at
                    - m.created_at
                )
            )
        ) <= 5
      );

-- ---------------------------------------------------------------------------
-- PRE-UPDATE HARD GUARDS
-- ---------------------------------------------------------------------------

do $$
declare
    v_historical_total integer;
    v_candidate_total integer;
    v_b_count integer;
    v_c_count integer;
    v_ambiguous_count integer;
    v_already_null integer;
begin
    select count(*)
      into v_historical_total
      from public.memories
     where created_at
           < timestamptz '2026-09-02 17:40:14+00';

    select count(*)
      into v_candidate_total
      from m35c2b_candidate_ids;

    select count(*)
      into v_b_count
      from m35c2b_candidate_ids
     where repair_class = 'B_migration_fingerprint';

    select count(*)
      into v_c_count
      from m35c2b_candidate_ids
     where repair_class = 'C_insert_default';

    select count(*)
      into v_already_null
      from public.memories
     where created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and last_confirmed_at is null;

    select count(*)
      into v_ambiguous_count
      from public.memories m
     where m.created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and m.last_confirmed_at is not null
       and not exists (
            select 1
              from m35c2b_candidate_ids c
             where c.id = m.id
       );

    if v_historical_total <> 127 then
        raise exception
            'M35c2b ABORT: historical total expected 127, got %',
            v_historical_total;
    end if;

    if v_candidate_total <> 106 then
        raise exception
            'M35c2b ABORT: candidate total expected 106, got %',
            v_candidate_total;
    end if;

    if v_b_count <> 37 then
        raise exception
            'M35c2b ABORT: B count expected 37, got %',
            v_b_count;
    end if;

    if v_c_count <> 69 then
        raise exception
            'M35c2b ABORT: C count expected 69, got %',
            v_c_count;
    end if;

    if v_ambiguous_count <> 21 then
        raise exception
            'M35c2b ABORT: ambiguous count expected 21, got %',
            v_ambiguous_count;
    end if;

    if v_already_null <> 0 then
        raise exception
            'M35c2b ABORT: expected 0 historical NULL timestamps, got %',
            v_already_null;
    end if;
end
$$;

-- ---------------------------------------------------------------------------
-- EXACT REPAIR
-- ---------------------------------------------------------------------------

do $$
declare
    v_repaired integer;
begin
    update public.memories m
       set last_confirmed_at = null
     where exists (
        select 1
          from m35c2b_candidate_ids c
         where c.id = m.id
     );

    get diagnostics v_repaired = row_count;

    if v_repaired <> 106 then
        raise exception
            'M35c2b ABORT: UPDATE expected 106 rows, changed %',
            v_repaired;
    end if;
end
$$;

-- ---------------------------------------------------------------------------
-- POST-UPDATE HARD GUARDS
-- ---------------------------------------------------------------------------

do $$
declare
    v_historical_total integer;
    v_null_count integer;
    v_remaining_timestamp_count integer;
    v_candidate_null_count integer;
begin
    select
        count(*),
        count(*) filter (
            where last_confirmed_at is null
        ),
        count(*) filter (
            where last_confirmed_at is not null
        )
    into
        v_historical_total,
        v_null_count,
        v_remaining_timestamp_count
    from public.memories
    where created_at
          < timestamptz '2026-09-02 17:40:14+00';

    select count(*)
      into v_candidate_null_count
      from public.memories m
      join m35c2b_candidate_ids c
        on c.id = m.id
     where m.last_confirmed_at is null;

    if v_historical_total <> 127 then
        raise exception
            'M35c2b ABORT: post total expected 127, got %',
            v_historical_total;
    end if;

    if v_candidate_null_count <> 106 then
        raise exception
            'M35c2b ABORT: expected all 106 candidates NULL, got %',
            v_candidate_null_count;
    end if;

    if v_null_count <> 106 then
        raise exception
            'M35c2b ABORT: historical NULL total expected 106, got %',
            v_null_count;
    end if;

    if v_remaining_timestamp_count <> 21 then
        raise exception
            'M35c2b ABORT: ambiguous timestamps expected 21, got %',
            v_remaining_timestamp_count;
    end if;
end
$$;

commit;
