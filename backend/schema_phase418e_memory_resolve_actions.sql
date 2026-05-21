-- Phase 4.18E — Memory resolve action schema support
-- Fixes POST /memory-review/quality/resolve failing when memories.archived_by
-- or memories.last_confirmed_at do not exist / are not visible to PostgREST.
--
-- Safe/idempotent.

alter table public.memories
    add column if not exists archived_by text;

alter table public.memories
    add column if not exists last_confirmed_at timestamptz;

create index if not exists memories_user_archived_by_idx
    on public.memories(user_id, archived_by);

create index if not exists memories_user_last_confirmed_idx
    on public.memories(user_id, last_confirmed_at desc);

notify pgrst, 'reload schema';
