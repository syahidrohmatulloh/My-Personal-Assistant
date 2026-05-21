-- Phase 4.18M — Local calendar event draft from memory candidates
--
-- Safe/idempotent:
-- - Adds nullable columns only if missing.
-- - Does not create Google Calendar events.
-- - Stores a confirmed local event draft that can later be synced to Google Calendar.

alter table public.memories
    add column if not exists calendar_event_status text;

alter table public.memories
    add column if not exists calendar_event_title text;

alter table public.memories
    add column if not exists calendar_event_date date;

alter table public.memories
    add column if not exists calendar_event_start_at timestamptz;

alter table public.memories
    add column if not exists calendar_event_end_at timestamptz;

alter table public.memories
    add column if not exists calendar_event_all_day boolean not null default false;

alter table public.memories
    add column if not exists calendar_event_created_at timestamptz;

create index if not exists memories_calendar_event_status_idx
    on public.memories(user_id, calendar_event_status, calendar_event_date desc);

notify pgrst, 'reload schema';
