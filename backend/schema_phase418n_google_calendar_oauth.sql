-- Phase 4.18N — Google Calendar OAuth foundation
--
-- Safe/idempotent:
-- - Adds OAuth state and calendar connection tables.
-- - Does not create Google Calendar events.
-- - Tokens are stored server-side only. Future phase should add encryption.

create extension if not exists pgcrypto;

create table if not exists public.google_oauth_states (
    state text primary key,
    user_id uuid not null,
    provider text not null default 'google_calendar',
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    used_at timestamptz
);

create index if not exists google_oauth_states_user_idx
    on public.google_oauth_states(user_id, created_at desc);

create index if not exists google_oauth_states_expires_idx
    on public.google_oauth_states(expires_at);

create table if not exists public.google_calendar_connections (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null unique,
    status text not null default 'active',
    email text,
    scope text,
    token_type text,
    access_token text,
    refresh_token text,
    expires_at timestamptz,
    connected_at timestamptz not null default now(),
    disconnected_at timestamptz,
    updated_at timestamptz not null default now()
);

create index if not exists google_calendar_connections_user_status_idx
    on public.google_calendar_connections(user_id, status);

notify pgrst, 'reload schema';
