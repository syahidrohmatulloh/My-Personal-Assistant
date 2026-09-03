-- =============================================================================
-- M35c2c — Historical Provenance Governance & Repair
--
-- Frozen corpus:
--   created_at < 2026-09-02 17:40:14+00
--
-- Audited corpus:
--   historical rows                 : 127
--   known deterministic inference   :   1
--   NULL provenance                 :  42
--   explicit historical plans       :  40
--   repair/quarantine total         :  83
--
-- Final historical provenance:
--   legacy_unknown                  :  82
--   system_inference                :   1
--   explicit_user_statement         :  29
--   repeated_pattern                :  10
--   user_answer_in_context          :   3
--   user_correction                 :   2
--
-- Only the one deterministically-proven system inference has confidence
-- capped to 0.54. legacy_unknown rows retain raw confidence for audit;
-- runtime governance caps their effective ranking confidence.
-- =============================================================================

begin;

lock table public.memories
    in share row exclusive mode;

-- Extend the storage taxonomy.
-- legacy_unknown is historical/audit-only and is not offered to writers.
do $$
declare
    constraint_row record;
begin
    for constraint_row in
        select c.conname
        from pg_constraint c
        join pg_class t
          on t.oid = c.conrelid
        join pg_namespace n
          on n.oid = t.relnamespace
        where n.nspname = 'public'
          and t.relname = 'memories'
          and c.contype = 'c'
          and pg_get_constraintdef(c.oid)
              ilike '%source_priority%'
    loop
        execute format(
            'alter table public.memories drop constraint %I',
            constraint_row.conname
        );
    end loop;
end
$$;

alter table public.memories
    add constraint memories_source_priority_check
    check (
        source_priority in (
            'explicit_user_statement',
            'user_answer_in_context',
            'user_correction',
            'repeated_pattern',
            'assistant_confirmation',
            'system_inference',
            'legacy_unknown'
        )
    );

create temporary table m35c2c_candidate_ids (
    id uuid primary key,
    repair_class text not null
        check (
            repair_class in (
                'known_system_inference',
                'legacy_null',
                'legacy_explicit_plan'
            )
        ),
    target_priority text not null
        check (
            target_priority in (
                'system_inference',
                'legacy_unknown'
            )
        )
) on commit drop;

insert into m35c2c_candidate_ids (
    id,
    repair_class,
    target_priority
)
select
    m.id,
    case
        when m.structured_field in (
            'aliyya_coding_support_style',
            'ui_design_taste',
            'aliyya_relationship_style',
            'debugging_support_style_under_frustration'
        )
        then 'known_system_inference'

        when m.source_priority is null
        then 'legacy_null'

        else 'legacy_explicit_plan'
    end,
    case
        when m.structured_field in (
            'aliyya_coding_support_style',
            'ui_design_taste',
            'aliyya_relationship_style',
            'debugging_support_style_under_frustration'
        )
        then 'system_inference'

        else 'legacy_unknown'
    end

from public.memories m

where m.created_at
      < timestamptz '2026-09-02 17:40:14+00'

  and (
        m.structured_field in (
            'aliyya_coding_support_style',
            'ui_design_taste',
            'aliyya_relationship_style',
            'debugging_support_style_under_frustration'
        )

        or m.source_priority is null

        or (
            m.source_priority = 'explicit_user_statement'
            and m.kind = 'plan'
        )
  );

-- ---------------------------------------------------------------------
-- PRE-REPAIR HARD GUARDS
-- ---------------------------------------------------------------------

do $$
declare
    v_historical_total integer;
    v_candidate_total integer;
    v_system_inference integer;
    v_legacy_null integer;
    v_explicit_plan integer;
    v_goal_reference integer;
    v_scheduled_event integer;
    v_unstructured_plan integer;
    v_preserve_explicit integer;
    v_preserve_repeated integer;
    v_preserve_direct integer;
    v_historical_active integer;
    v_candidate_active integer;
    v_null_timestamps integer;
    v_preserved_timestamps integer;
begin
    select count(*)
      into v_historical_total
      from public.memories
     where created_at
           < timestamptz '2026-09-02 17:40:14+00';

    select count(*)
      into v_candidate_total
      from m35c2c_candidate_ids;

    select count(*)
      into v_system_inference
      from m35c2c_candidate_ids
     where repair_class = 'known_system_inference';

    select count(*)
      into v_legacy_null
      from m35c2c_candidate_ids
     where repair_class = 'legacy_null';

    select count(*)
      into v_explicit_plan
      from m35c2c_candidate_ids
     where repair_class = 'legacy_explicit_plan';

    select count(*)
      into v_goal_reference
      from public.memories m
      join m35c2c_candidate_ids c
        on c.id = m.id
     where c.repair_class = 'legacy_explicit_plan'
       and m.structured_field = 'active_goal_reference';

    select count(*)
      into v_scheduled_event
      from public.memories m
      join m35c2c_candidate_ids c
        on c.id = m.id
     where c.repair_class = 'legacy_explicit_plan'
       and m.structured_field = 'scheduled_event';

    select count(*)
      into v_unstructured_plan
      from public.memories m
      join m35c2c_candidate_ids c
        on c.id = m.id
     where c.repair_class = 'legacy_explicit_plan'
       and m.structured_field is null;

    select count(*)
      into v_preserve_explicit
      from public.memories m
     where m.created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and m.source_priority = 'explicit_user_statement'
       and not exists (
            select 1
              from m35c2c_candidate_ids c
             where c.id = m.id
       );

    select count(*)
      into v_preserve_repeated
      from public.memories m
     where m.created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and m.source_priority = 'repeated_pattern';

    select count(*)
      into v_preserve_direct
      from public.memories m
     where m.created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and m.source_priority in (
            'user_answer_in_context',
            'user_correction'
       );

    select count(*)
      into v_historical_active
      from public.memories m
     where m.created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and m.deleted_at is null
       and coalesce(m.archived, false) = false
       and coalesce(m.superseded, false) = false
       and lower(coalesce(m.status, 'active'))
           not in ('archived', 'superseded', 'deleted');

    select count(*)
      into v_candidate_active
      from public.memories m
      join m35c2c_candidate_ids c
        on c.id = m.id
     where m.deleted_at is null
       and coalesce(m.archived, false) = false
       and coalesce(m.superseded, false) = false
       and lower(coalesce(m.status, 'active'))
           not in ('archived', 'superseded', 'deleted');

    select
        count(*) filter (
            where last_confirmed_at is null
        ),
        count(*) filter (
            where last_confirmed_at is not null
        )
    into
        v_null_timestamps,
        v_preserved_timestamps
    from public.memories
    where created_at
          < timestamptz '2026-09-02 17:40:14+00';

    if v_historical_total <> 127 then
        raise exception
            'M35c2c ABORT: historical total expected 127, got %',
            v_historical_total;
    end if;

    if v_candidate_total <> 83 then
        raise exception
            'M35c2c ABORT: repair candidates expected 83, got %',
            v_candidate_total;
    end if;

    if v_system_inference <> 1 then
        raise exception
            'M35c2c ABORT: known inference expected 1, got %',
            v_system_inference;
    end if;

    if v_legacy_null <> 42 then
        raise exception
            'M35c2c ABORT: legacy NULL expected 42, got %',
            v_legacy_null;
    end if;

    if v_explicit_plan <> 40 then
        raise exception
            'M35c2c ABORT: explicit plan expected 40, got %',
            v_explicit_plan;
    end if;

    if v_goal_reference <> 1
       or v_scheduled_event <> 36
       or v_unstructured_plan <> 3
    then
        raise exception
            'M35c2c ABORT: plan fingerprint expected 1/36/3, got %/%/%',
            v_goal_reference,
            v_scheduled_event,
            v_unstructured_plan;
    end if;

    if v_preserve_explicit <> 29 then
        raise exception
            'M35c2c ABORT: preserved explicit expected 29, got %',
            v_preserve_explicit;
    end if;

    if v_preserve_repeated <> 10 then
        raise exception
            'M35c2c ABORT: repeated expected 10, got %',
            v_preserve_repeated;
    end if;

    if v_preserve_direct <> 5 then
        raise exception
            'M35c2c ABORT: direct-user expected 5, got %',
            v_preserve_direct;
    end if;

    if v_historical_active <> 64 then
        raise exception
            'M35c2c ABORT: historical active expected 64, got %',
            v_historical_active;
    end if;

    if v_candidate_active <> 39 then
        raise exception
            'M35c2c ABORT: active repair candidates expected 39, got %',
            v_candidate_active;
    end if;

    -- Proves M35c2b is the baseline.
    if v_null_timestamps <> 106
       or v_preserved_timestamps <> 21
    then
        raise exception
            'M35c2c ABORT: confirmation baseline expected 106/21, got %/%',
            v_null_timestamps,
            v_preserved_timestamps;
    end if;
end
$$;

-- ---------------------------------------------------------------------
-- SINGLE HISTORICAL REPAIR
-- ---------------------------------------------------------------------

do $$
declare
    v_repaired integer;
begin
    update public.memories m
       set source_priority = c.target_priority,
           confidence = case
               when c.repair_class = 'known_system_inference'
               then least(
                    coalesce(m.confidence, 0.54::real),
                    0.54::real
                )
               else m.confidence
           end
      from m35c2c_candidate_ids c
     where c.id = m.id;

    get diagnostics v_repaired = row_count;

    if v_repaired <> 83 then
        raise exception
            'M35c2c ABORT: expected 83 repaired rows, changed %',
            v_repaired;
    end if;
end
$$;

-- ---------------------------------------------------------------------
-- POST-REPAIR HARD GUARDS
-- ---------------------------------------------------------------------

do $$
declare
    v_total integer;
    v_legacy_unknown integer;
    v_system_inference integer;
    v_explicit integer;
    v_repeated integer;
    v_answer integer;
    v_correction integer;
    v_null_provenance integer;
    v_active_legacy_unknown integer;
    v_active_system_inference integer;
    v_capped_system_inference integer;
    v_null_timestamps integer;
    v_preserved_timestamps integer;
begin
    select
        count(*),
        count(*) filter (
            where source_priority = 'legacy_unknown'
        ),
        count(*) filter (
            where source_priority = 'system_inference'
        ),
        count(*) filter (
            where source_priority = 'explicit_user_statement'
        ),
        count(*) filter (
            where source_priority = 'repeated_pattern'
        ),
        count(*) filter (
            where source_priority = 'user_answer_in_context'
        ),
        count(*) filter (
            where source_priority = 'user_correction'
        ),
        count(*) filter (
            where source_priority is null
        ),
        count(*) filter (
            where last_confirmed_at is null
        ),
        count(*) filter (
            where last_confirmed_at is not null
        )
    into
        v_total,
        v_legacy_unknown,
        v_system_inference,
        v_explicit,
        v_repeated,
        v_answer,
        v_correction,
        v_null_provenance,
        v_null_timestamps,
        v_preserved_timestamps
    from public.memories
    where created_at
          < timestamptz '2026-09-02 17:40:14+00';

    select count(*)
      into v_active_legacy_unknown
      from public.memories m
     where m.created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and m.source_priority = 'legacy_unknown'
       and m.deleted_at is null
       and coalesce(m.archived, false) = false
       and coalesce(m.superseded, false) = false
       and lower(coalesce(m.status, 'active'))
           not in ('archived', 'superseded', 'deleted');

    select count(*)
      into v_active_system_inference
      from public.memories m
     where m.created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and m.source_priority = 'system_inference'
       and m.deleted_at is null
       and coalesce(m.archived, false) = false
       and coalesce(m.superseded, false) = false
       and lower(coalesce(m.status, 'active'))
           not in ('archived', 'superseded', 'deleted');

    select count(*)
      into v_capped_system_inference
      from public.memories
     where created_at
           < timestamptz '2026-09-02 17:40:14+00'
       and source_priority = 'system_inference'
       and confidence <= 0.54::real;

    if v_total <> 127
       or v_legacy_unknown <> 82
       or v_system_inference <> 1
       or v_explicit <> 29
       or v_repeated <> 10
       or v_answer <> 3
       or v_correction <> 2
       or v_null_provenance <> 0
    then
        raise exception
            'M35c2c ABORT: post provenance distribution mismatch';
    end if;

    if v_active_legacy_unknown <> 38
       or v_active_system_inference <> 1
    then
        raise exception
            'M35c2c ABORT: active quarantine expected 38/1, got %/%',
            v_active_legacy_unknown,
            v_active_system_inference;
    end if;

    if v_capped_system_inference <> 1 then
        raise exception
            'M35c2c ABORT: system inference confidence cap failed';
    end if;

    -- Provenance repair must not rewrite confirmation history.
    if v_null_timestamps <> 106
       or v_preserved_timestamps <> 21
    then
        raise exception
            'M35c2c ABORT: confirmation distribution changed';
    end if;
end
$$;

commit;
