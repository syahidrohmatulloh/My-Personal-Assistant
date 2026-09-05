-- =============================================================================
-- M35C3 — Memory Confirmation / Provenance UX Governance
--
-- Core authority rule:
--
--     historical last_confirmed_at != genuine user confirmation
--
-- This migration introduces a separate canonical authority signal.
--
-- IMPORTANT:
--   * NO backfill from last_confirmed_at.
--   * NO historical memory content mutation.
--   * NO lifecycle mutation.
-- =============================================================================

begin;

alter table public.memories
    add column if not exists last_user_confirmed_at timestamptz,
    add column if not exists last_user_confirmation_source text,
    add column if not exists last_user_confirmation_evidence jsonb;

comment on column public.memories.last_user_confirmed_at is
    'Timestamp of genuine user evidence explicitly confirming an existing memory. Never backfilled from legacy last_confirmed_at.';

comment on column public.memories.last_user_confirmation_source is
    'Auditable source of genuine confirmation such as memory_review, chat_restatement, or quality_resolution.';

comment on column public.memories.last_user_confirmation_evidence is
    'Audit-safe structured evidence describing the user action that established confirmation.';

alter table public.memories
    drop constraint if exists memories_last_user_confirmation_source_check;

alter table public.memories
    add constraint memories_last_user_confirmation_source_check
    check (
        last_user_confirmation_source is null
        or last_user_confirmation_source in (
            'memory_review',
            'chat_restatement',
            'quality_resolution'
        )
    );

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
    updated_at timestamptz,
    similarity double precision,
    category text,
    confidence real,
    structured_field text,
    structured_value text,
    superseded boolean,
    source_priority text,
    status text,
    archived boolean,
    deleted_at timestamptz,
    last_user_confirmed_at timestamptz,
    last_user_confirmation_source text,
    last_user_confirmation_evidence jsonb
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
        m.updated_at,
        1 - (m.embedding <=> p_query_embedding) as similarity,
        m.category,
        m.confidence::real as confidence,
        m.structured_field,
        m.structured_value,
        coalesce(m.superseded, false) as superseded,
        m.source_priority,
        m.status,
        coalesce(m.archived, false) as archived,
        m.deleted_at,
        m.last_user_confirmed_at,
        m.last_user_confirmation_source,
        m.last_user_confirmation_evidence
    from public.memories m
    where m.user_id = p_user_id
      and m.embedding is not null
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
