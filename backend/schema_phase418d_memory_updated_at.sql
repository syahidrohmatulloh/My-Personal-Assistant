-- Phase 4.18D — Memory updated_at schema support
-- Fixes memory_health_scheduler querying memories.updated_at when the column
-- does not exist yet.
--
-- Safe/idempotent:
-- - Adds updated_at only if missing.
-- - Backfills from created_at when available.
-- - Adds trigger to keep updated_at fresh.
-- - Adds indexes only if missing.

alter table public.memories
    add column if not exists updated_at timestamptz;

update public.memories
set updated_at = coalesce(created_at, now())
where updated_at is null;

alter table public.memories
    alter column updated_at set default now(),
    alter column updated_at set not null;

create or replace function public.set_memories_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists memories_updated_at on public.memories;

create trigger memories_updated_at
before update on public.memories
for each row
execute function public.set_memories_updated_at();

create index if not exists memories_user_updated_at_idx
    on public.memories(user_id, updated_at desc);

create index if not exists memories_updated_at_idx
    on public.memories(updated_at desc);
