-- =============================================================================
-- Phase 4.5: Conversation-level summaries for cross-chat continuity.
--
-- Adds three columns to `conversations`:
--   - summary             : a 2-4 sentence recap, written by Haiku
--   - summary_embedding   : Voyage embedding for semantic search across chats
--   - summarized_through  : last message ID we summarized to (lets us re-run
--                           summarization incrementally without re-embedding
--                           old messages each time)
--   - summarized_at       : when we last updated the summary
--
-- Run once, in Supabase SQL Editor. Safe to re-run (uses IF NOT EXISTS).
-- =============================================================================

alter table conversations
    add column if not exists summary text,
    add column if not exists summary_embedding vector(1024),
    add column if not exists summarized_through uuid references messages(id) on delete set null,
    add column if not exists summarized_at timestamptz;

-- ivfflat index for cross-conversation semantic search.
-- Small lists value because most users will have <100 summarized conversations.
create index if not exists conversations_summary_embedding_idx
    on conversations using ivfflat (summary_embedding vector_cosine_ops)
    with (lists = 10);

-- =============================================================================
-- RPC: find conversations with summaries semantically close to a query.
-- Caller passes the user's question (embedded) — we return top N other
-- conversation summaries that may carry useful prior context.
-- =============================================================================

create or replace function match_conversation_summaries(
    p_user_id uuid,
    p_query_embedding vector(1024),
    p_exclude_id uuid,            -- the current conversation (skip self)
    p_match_count int default 3,
    p_min_similarity float default 0.55
)
returns table (
    id uuid,
    title text,
    summary text,
    updated_at timestamptz,
    similarity float
)
language sql
stable
as $$
    select
        c.id,
        c.title,
        c.summary,
        c.updated_at,
        1 - (c.summary_embedding <=> p_query_embedding) as similarity
    from conversations c
    where c.user_id = p_user_id
      and c.id <> p_exclude_id
      and c.summary is not null
      and c.summary_embedding is not null
      and 1 - (c.summary_embedding <=> p_query_embedding) >= p_min_similarity
    order by c.summary_embedding <=> p_query_embedding
    limit p_match_count;
$$;
