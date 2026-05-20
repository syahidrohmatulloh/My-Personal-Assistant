-- Phase 4.17B — Assistant avatar image upload storage
-- Creates a Supabase Storage bucket for user-owned assistant avatar images.
-- Client paths should be scoped as: {auth.uid()}/{generated_filename}

insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values (
    'assistant-avatars',
    'assistant-avatars',
    true,
    5242880,
    array['image/jpeg', 'image/png', 'image/webp']::text[]
)
on conflict (id) do update set
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "assistant_avatars_select_own" on storage.objects;
create policy "assistant_avatars_select_own"
    on storage.objects
    for select
    using (
        bucket_id = 'assistant-avatars'
        and auth.uid()::text = (storage.foldername(name))[1]
    );

drop policy if exists "assistant_avatars_insert_own" on storage.objects;
create policy "assistant_avatars_insert_own"
    on storage.objects
    for insert
    with check (
        bucket_id = 'assistant-avatars'
        and auth.uid()::text = (storage.foldername(name))[1]
    );

drop policy if exists "assistant_avatars_update_own" on storage.objects;
create policy "assistant_avatars_update_own"
    on storage.objects
    for update
    using (
        bucket_id = 'assistant-avatars'
        and auth.uid()::text = (storage.foldername(name))[1]
    )
    with check (
        bucket_id = 'assistant-avatars'
        and auth.uid()::text = (storage.foldername(name))[1]
    );

drop policy if exists "assistant_avatars_delete_own" on storage.objects;
create policy "assistant_avatars_delete_own"
    on storage.objects
    for delete
    using (
        bucket_id = 'assistant-avatars'
        and auth.uid()::text = (storage.foldername(name))[1]
    );
