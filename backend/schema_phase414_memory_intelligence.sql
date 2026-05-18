-- =============================================================================
-- Phase 4.14 — Memory intelligence columns
--
-- Adds metadata to `memories` so we can support:
--   - confidence scoring
--   - source priority (explicit > answer in context > correction > pattern > assistant)
--   - evidence snippets (quotes that back this memory)
--   - category beyond the legacy 'kind' enum (identity, preferences, ...)
--   - supersede chain (when a new fact contradicts an old one)
--   - last_confirmed_at (when did we last see signal supporting this)
--
-- Backwards compatible: all new columns nullable or default. Existing rows
-- and existing memory.py code continue to work unchanged.
--
-- Idempotent: re-running is safe via `if not exists`.
-- =============================================================================

-- Confidence score (0-1). High = we're sure. Low = soft signal.
alter table memories
    add column if not exists confidence real check (confidence between 0 and 1);

-- Source priority labels — controlled enum.
-- explicit_user_statement: user directly told us ("my birthday is 7 Jan")
-- user_answer_in_context:   user answered an assistant question ("7 Januari hehe")
-- user_correction:           user said "actually, it's X not Y"
-- repeated_pattern:          observed multiple times in past conversations
-- assistant_confirmation:    user only acknowledged something assistant said (low signal)
alter table memories
    add column if not exists source_priority text
    check (source_priority in (
        'explicit_user_statement',
        'user_answer_in_context',
        'user_correction',
        'repeated_pattern',
        'assistant_confirmation'
    ));

-- Evidence: short quotes from the conversation that back this memory.
-- Stored as jsonb array of strings. Capped at 3 entries by the service.
alter table memories
    add column if not exists evidence jsonb default '[]'::jsonb;

-- Semantic category — orthogonal to `kind` (which we keep for backwards compat).
-- Categories: identity, preferences, relationships, routines, goals,
--             important_dates, constraints, other.
alter table memories
    add column if not exists category text
    check (category in (
        'identity',
        'preferences',
        'relationships',
        'routines',
        'goals',
        'important_dates',
        'constraints',
        'other'
    ));

-- Supersede chain. When a new fact contradicts an old one we mark the old
-- superseded=true and point superseded_by to the new memory.id. The agent
-- queries WHERE superseded=false to read only the current truth.
alter table memories
    add column if not exists superseded boolean default false not null;

alter table memories
    add column if not exists superseded_by uuid references memories(id) on delete set null;

alter table memories
    add column if not exists superseded_at timestamptz;

-- last_confirmed_at: rolling timestamp updated when we see new evidence
-- supporting an existing memory (instead of creating duplicates).
alter table memories
    add column if not exists last_confirmed_at timestamptz default now();

-- structured_field: identifies which user-identity field this memory
-- represents, e.g. 'birthday', 'timezone', 'nickname'. NULL for unstructured.
-- Enables deterministic supersede on identity facts (find old birthday row
-- without ILIKE guesswork).
alter table memories
    add column if not exists structured_field text;

-- structured_value: the actual value, e.g. '7 Januari'. Mirrors what we
-- merge into user_identity.profile so we can audit divergence.
alter table memories
    add column if not exists structured_value text;

-- Index on superseded=false for the common read path (active memories only).
create index if not exists memories_user_active_idx
    on memories (user_id, created_at desc)
    where superseded = false;

-- Index for fast deterministic supersede lookup on structured identity facts.
-- Filtered (partial) — only indexes rows that have structured_field set, which
-- is a small subset of total memories.
create index if not exists memories_user_structured_field_active_idx
    on memories (user_id, structured_field, created_at desc)
    where superseded = false and structured_field is not null;
