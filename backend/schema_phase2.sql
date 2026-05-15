-- Phase 2: memory across conversations.
-- Run this in Supabase → SQL Editor → New query.
-- Safe to run more than once.

-- ============================================================================
-- pgvector — enables vector similarity search inside Postgres.
-- ============================================================================

create extension if not exists vector;

-- ============================================================================
-- memories table
--
-- Stores facts Claude has learned about you, with embeddings for semantic
-- search. Each row is one durable thing — "user lives in Jakarta", "user
-- prefers concise replies", etc.
--
-- Columns:
--   content  — the fact itself, in plain English
--   kind     — fact / preference / context — lets the UI group them
--   embedding — 1024-dim vector from voyage-3.5-lite, used for similarity search
--   source   — 'auto' (Claude extracted) or 'manual' (you typed it)
--   source_conversation_id — which chat this came from, nullable
-- ============================================================================

create table if not exists memories (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users not null,
    content text not null,
    kind text not null default 'fact' check (kind in ('fact', 'preference', 'context')),
    embedding vector(1024),
    source text not null default 'auto' check (source in ('auto', 'manual')),
    source_conversation_id uuid references conversations on delete set null,
    created_at timestamptz default now() not null
);

-- Index for fast user-scoped queries.
create index if not exists memories_user_id_created_at_idx
    on memories (user_id, created_at desc);

-- Index for fast cosine similarity search.
-- ivfflat is good for up to ~1M vectors; for personal use it's overkill but
-- correct. The `lists` parameter is a tuning knob — 100 is fine for small data.
create index if not exists memories_embedding_idx
    on memories using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- ============================================================================
-- Row-Level Security
-- ============================================================================

alter table memories enable row level security;

drop policy if exists "own memories" on memories;

create policy "own memories" on memories
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- ============================================================================
-- RPC: search memories by vector similarity
--
-- We expose this as a Postgres function because pgvector's `<=>` operator
-- syntax is awkward to express through the supabase-py builder. Calling
-- a function is cleaner.
--
-- Returns the top-N most semantically similar memories for a user, with a
-- similarity score (higher = more similar).
-- ============================================================================

create or replace function match_memories(
    p_user_id uuid,
    p_query_embedding vector(1024),
    p_match_count int default 8
)
returns table (
    id uuid,
    content text,
    kind text,
    similarity float
)
language sql
stable
as $$
    select
        m.id,
        m.content,
        m.kind,
        1 - (m.embedding <=> p_query_embedding) as similarity
    from memories m
    where m.user_id = p_user_id
      and m.embedding is not null
    order by m.embedding <=> p_query_embedding
    limit p_match_count;
$$;
