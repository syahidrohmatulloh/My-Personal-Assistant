-- =============================================================================
-- Memory decay — Principle 2: inferred conclusions weaken over time
--
-- This implements gentle confidence decay on AI-inferred rows. Run periodically
-- (weekly is fine) via Supabase pg_cron. The decay is conservative: -0.05 per
-- 30 days of age, floor at 0.1. Self-reported rows are never decayed.
--
-- Run this AFTER schema_phase3.sql.
-- =============================================================================

create or replace function decay_inferred_confidence()
returns table (table_name text, rows_affected bigint)
language plpgsql
as $$
declare
    affected bigint;
begin
    -- emotional_state: only inferred rows, only non-superseded, only > 30 days old.
    update emotional_state
    set confidence = greatest(0.1, confidence - 0.05)
    where source = 'inferred'
      and superseded = false
      and observed_at < now() - interval '30 days'
      and confidence > 0.1;
    get diagnostics affected = row_count;
    return query select 'emotional_state'::text, affected;

    -- relationship_notes
    update relationship_notes
    set confidence = greatest(0.1, confidence - 0.05)
    where source = 'inferred'
      and superseded = false
      and created_at < now() - interval '30 days'
      and confidence > 0.1;
    get diagnostics affected = row_count;
    return query select 'relationship_notes'::text, affected;
end;
$$;

-- To schedule this with pg_cron (Supabase has pg_cron available on free tier):
--
--   select cron.schedule(
--       'decay-inferred-confidence',
--       '0 3 * * 0',  -- Sunday 03:00 UTC
--       'select decay_inferred_confidence()'
--   );
--
-- Run that in the SQL editor once you're ready to enable scheduled decay.
-- It's safe to leave decay manual for now (call the function from a workflow
-- in a later phase) — RUNS DON'T have to be automatic to be useful.
