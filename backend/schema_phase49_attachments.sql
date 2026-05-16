-- =============================================================================
-- Phase 4.9: Message attachments (images, PDFs)
--
-- Stores metadata only. Actual file bytes live in Supabase Storage
-- in the private `attachments` bucket. The `storage_path` column
-- points to the file path within that bucket.
--
-- A single message can carry multiple attachments (e.g. 3 photos at once).
-- Attachments without a message_id are "pending" — uploaded but not yet
-- sent. We clean those up via cron (not in this migration).
-- =============================================================================

create table if not exists message_attachments (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    message_id uuid references messages(id) on delete cascade,  -- null = pending

    storage_path text not null,           -- "<user_id>/<uuid>.<ext>"
    original_filename text not null,
    media_type text not null,             -- 'image/jpeg' | 'image/png' | 'application/pdf' | ...
    kind text not null check (kind in ('image', 'document')),
    size_bytes bigint not null,

    -- Auto-generated description from Haiku (images only). Used to inject
    -- context into memories so the assistant "remembers" what was shown.
    description text,

    created_at timestamptz not null default now()
);

create index if not exists message_attachments_message_id_idx
    on message_attachments (message_id) where message_id is not null;
create index if not exists message_attachments_user_id_pending_idx
    on message_attachments (user_id, created_at desc) where message_id is null;

-- =============================================================================
-- Storage bucket
--
-- Run this ONCE in the Supabase dashboard (Storage → New bucket) OR via SQL
-- below. The bucket must be PRIVATE — service role only.
--
-- Backend uses service role key to upload/download; frontend never touches
-- this bucket directly.
-- =============================================================================

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'attachments',
    'attachments',
    false,
    20971520,  -- 20MB hard ceiling at storage layer (we enforce smaller in app)
    array[
        'image/jpeg', 'image/png', 'image/gif', 'image/webp',
        'application/pdf'
    ]
)
on conflict (id) do update set
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- No RLS policies on the bucket — service role bypasses RLS. We control
-- access entirely in the backend by filtering by user_id.
