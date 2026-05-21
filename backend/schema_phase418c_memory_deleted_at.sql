-- Phase 4.18C — Memory deleted_at schema support
-- Fixes memory_health_scheduler querying memories.deleted_at when the column
-- does not exist yet.
--
-- Safe/idempotent:
-- - Adds deleted_at only if missing.
-- - Adds indexes only if missing.

alter table public.memories
    add column if not exists deleted_at timestamptz;

create index if not exists memories_user_deleted_at_created_idx
    on public.memories(user_id, deleted_at, created_at desc);

create index if not exists memories_deleted_at_idx
    on public.memories(deleted_at);
