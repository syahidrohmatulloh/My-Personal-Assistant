-- Run this in your Supabase project's SQL editor.
-- Dashboard → SQL Editor → New Query → paste this → Run.

-- ============================================================================
-- Tables
-- ============================================================================

create table if not exists conversations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users not null,
    title text default 'New chat' not null,
    created_at timestamptz default now() not null,
    updated_at timestamptz default now() not null
);

create index if not exists conversations_user_id_updated_at_idx
    on conversations (user_id, updated_at desc);

create table if not exists messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid references conversations on delete cascade not null,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    created_at timestamptz default now() not null
);

create index if not exists messages_conversation_id_created_at_idx
    on messages (conversation_id, created_at);

-- ============================================================================
-- Row-Level Security
--
-- This is critical. RLS makes Postgres itself enforce "users can only see
-- their own data". Even if your code has a bug, the database refuses to leak.
-- ============================================================================

alter table conversations enable row level security;
alter table messages enable row level security;

-- Drop existing policies if re-running this script.
drop policy if exists "own conversations" on conversations;
drop policy if exists "own messages" on messages;

create policy "own conversations" on conversations
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create policy "own messages" on messages
    for all
    using (
        conversation_id in (select id from conversations where user_id = auth.uid())
    )
    with check (
        conversation_id in (select id from conversations where user_id = auth.uid())
    );
