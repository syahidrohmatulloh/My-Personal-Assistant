-- Phase 4.18J — Time-bound memory lifecycle
-- Adds lifecycle metadata for scheduled/time-bound memories.
--
-- Safe/idempotent:
-- - Adds nullable columns only if missing.
-- - Does not delete or archive data.
-- - Existing memories are backfilled by tools/backfill_time_bound_memories.py.

alter table public.memories
    add column if not exists lifecycle_type text;

alter table public.memories
    add column if not exists due_date date;

alter table public.memories
    add column if not exists expires_at timestamptz;

alter table public.memories
    add column if not exists calendar_candidate boolean not null default false;

create index if not exists memories_user_lifecycle_idx
    on public.memories(user_id, lifecycle_type, due_date desc);

create index if not exists memories_calendar_candidate_idx
    on public.memories(user_id, calendar_candidate, due_date desc)
    where calendar_candidate = true;

create index if not exists memories_expires_at_idx
    on public.memories(expires_at)
    where expires_at is not null;

notify pgrst, 'reload schema';
