-- Calendar vNext — Structured Event Location
--
-- Safe/idempotent:
-- - Adds a single nullable column only if missing.
-- - No data is modified; backfill is handled separately by
--   backend/tools/backfill_calendar_event_locations.py (dry-run first).
--
-- Run in the Supabase SQL Editor BEFORE deploying backend code that writes
-- or selects calendar_event_location.

alter table public.memories
    add column if not exists calendar_event_location text;

notify pgrst, 'reload schema';
