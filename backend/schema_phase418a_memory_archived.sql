-- Phase 4.18A — Memory archived schema support
-- Fixes memory_health_scheduler querying memories.archived when the column
-- does not exist yet.
--
-- Safe/idempotent:
-- - Adds columns only if missing.
-- - Backfills archived=false for existing rows.
-- - Adds indexes only if missing.

alter table public.memories
    add column if not exists archived boolean;

update public.memories
set archived = false
where archived is null;

alter table public.memories
    alter column archived set default false,
    alter column archived set not null;

alter table public.memories
    add column if not exists archived_at timestamptz;

create index if not exists memories_user_archived_created_idx
    on public.memories(user_id, archived, created_at desc);

create index if not exists memories_archived_idx
    on public.memories(archived);
