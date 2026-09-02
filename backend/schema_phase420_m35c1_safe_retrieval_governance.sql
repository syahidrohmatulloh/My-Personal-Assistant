-- =============================================================================
-- M35c1 — Safe Retrieval Governance Contract Repair
--
-- Evidence from M35b:
--   * lifecycle-hidden rows can cross the current RPC boundary;
--   * source_priority, status, archived/deleted state are not fully projected;
--   * historical last_confirmed_at is contaminated and MUST NOT become a new
--     retrieval trust/recency signal before historical repair.
--
-- Scope:
--   * repair the match_memories retrieval contract only;
--   * filter lifecycle-hidden memories before they leave Postgres;
--   * project provenance and lifecycle metadata required by Python governance;
--   * intentionally omit last_confirmed_at until M35c2;
--   * no historical data mutation or backfill.
--
-- Safe failure behavior:
--   The DROP + CREATE run in one transaction. If recreation fails, the
--   transaction rolls back and the previous function remains intact.
-- =============================================================================

begin;

drop function if exists public.match_memories(
    uuid,
    vector(1024),
    integer
);

create function public.match_memories(
    p_user_id uuid,
    p_query_embedding vector(1024),
    p_match_count integer
)
returns table (
    id uuid,
    content text,
    kind text,
    source text,
    source_conversation_id uuid,
    created_at timestamptz,
    similarity double precision,
    category text,
    confidence real,
    structured_field text,
    structured_value text,
    superseded boolean,
    source_priority text,
    status text,
    archived boolean,
    deleted_at timestamptz
)
language sql
stable
as $$
    select
        m.id,
        m.content,
        m.kind,
        m.source,
        m.source_conversation_id,
        m.created_at,
        1 - (m.embedding <=> p_query_embedding) as similarity,
        m.category,
        m.confidence::real as confidence,
        m.structured_field,
        m.structured_value,
        coalesce(m.superseded, false) as superseded,
        m.source_priority,
        m.status,
        coalesce(m.archived, false) as archived,
        m.deleted_at
    from public.memories m
    where m.user_id = p_user_id
      and m.embedding is not null

      -- Canonical lifecycle-hidden states must never cross the retrieval
      -- boundary. Python retains the same checks as defense in depth.
      and coalesce(m.superseded, false) = false
      and coalesce(m.archived, false) = false
      and m.deleted_at is null
      and lower(coalesce(m.status, 'active')) not in (
          'archived',
          'superseded',
          'deleted'
      )

    order by m.embedding <=> p_query_embedding
    limit p_match_count;
$$;

notify pgrst, 'reload schema';

commit;
