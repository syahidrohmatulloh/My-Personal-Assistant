-- Phase 4.18P — Sync local calendar draft to Google Calendar
--
-- Safe/idempotent:
-- - Adds nullable Google Calendar sync metadata columns.
-- - Does not create Google events by itself.
-- - App creates events only after explicit user action + Memory PIN.

alter table public.memories
    add column if not exists google_calendar_event_id text;

alter table public.memories
    add column if not exists google_calendar_event_link text;

alter table public.memories
    add column if not exists google_calendar_id text;

alter table public.memories
    add column if not exists calendar_synced_at timestamptz;

alter table public.memories
    add column if not exists calendar_sync_error text;

create index if not exists memories_google_calendar_event_id_idx
    on public.memories(user_id, google_calendar_event_id)
    where google_calendar_event_id is not null;

create index if not exists memories_calendar_synced_idx
    on public.memories(user_id, calendar_synced_at desc)
    where calendar_synced_at is not null;

notify pgrst, 'reload schema';
