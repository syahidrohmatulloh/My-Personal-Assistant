-- Phase 4.18B — Memory status schema support
-- Fixes memory_health_scheduler querying memories.status when the column
-- does not exist yet.
--
-- Safe/idempotent:
-- - Adds status only if missing.
-- - Backfills existing rows to active.
-- - Adds a constrained status domain.
-- - Adds indexes used by health/review queries.

alter table public.memories
    add column if not exists status text;

update public.memories
set status = 'active'
where status is null;

alter table public.memories
    alter column status set default 'active',
    alter column status set not null;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'memories_status_check'
    ) then
        alter table public.memories
            add constraint memories_status_check
            check (status in ('active', 'archived', 'dismissed', 'superseded'));
    end if;
end $$;

create index if not exists memories_user_status_created_idx
    on public.memories(user_id, status, created_at desc);

create index if not exists memories_status_idx
    on public.memories(status);
