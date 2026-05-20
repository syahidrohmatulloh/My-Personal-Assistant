-- Phase 4.17A — AI Avatar Mode foundation
-- Safe foundation only: stores avatar display settings.
-- No face cloning, no deepfake generation, no talking-video generation.

create table if not exists public.assistant_avatar_profiles (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    image_url text,
    avatar_mode_enabled boolean not null default false,
    consent_confirmed boolean not null default false,
    animation_style text not null default 'calm',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint assistant_avatar_profiles_user_unique unique (user_id),
    constraint assistant_avatar_profiles_animation_style_check
        check (animation_style in ('calm', 'subtle', 'minimal')),
    constraint assistant_avatar_profiles_image_url_len
        check (image_url is null or char_length(image_url) <= 2048)
);

create index if not exists assistant_avatar_profiles_user_id_idx
    on public.assistant_avatar_profiles(user_id);

create index if not exists assistant_avatar_profiles_user_updated_idx
    on public.assistant_avatar_profiles(user_id, updated_at desc);

alter table public.assistant_avatar_profiles enable row level security;

drop policy if exists "assistant_avatar_profiles_select_own" on public.assistant_avatar_profiles;
create policy "assistant_avatar_profiles_select_own"
    on public.assistant_avatar_profiles
    for select
    using (auth.uid() = user_id);

drop policy if exists "assistant_avatar_profiles_insert_own" on public.assistant_avatar_profiles;
create policy "assistant_avatar_profiles_insert_own"
    on public.assistant_avatar_profiles
    for insert
    with check (auth.uid() = user_id);

drop policy if exists "assistant_avatar_profiles_update_own" on public.assistant_avatar_profiles;
create policy "assistant_avatar_profiles_update_own"
    on public.assistant_avatar_profiles
    for update
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

drop policy if exists "assistant_avatar_profiles_delete_own" on public.assistant_avatar_profiles;
create policy "assistant_avatar_profiles_delete_own"
    on public.assistant_avatar_profiles
    for delete
    using (auth.uid() = user_id);

create or replace function public.set_assistant_avatar_profiles_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists assistant_avatar_profiles_updated_at on public.assistant_avatar_profiles;
create trigger assistant_avatar_profiles_updated_at
before update on public.assistant_avatar_profiles
for each row
execute function public.set_assistant_avatar_profiles_updated_at();
