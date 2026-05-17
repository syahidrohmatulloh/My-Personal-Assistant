-- =============================================================================
-- Phase 4.12: Companion settings & mood state
--
-- Replaces two ChatGPT-era tables that were never committed to repo:
--   - `user_state` (mostly dead code, never wired to chat.py)
--   - `companion_mood_states` (had useful columns but conversation-scoped state
--     created split-personality bugs)
--
-- New design:
--   1. `companion_settings` — stable preferences (mode, name, toggles)
--   2. `companion_mood_state` — current dynamic mood, one row per user, TTL
--
-- Opt-in escalation ladder enforced by service layer (not DB constraint, so
-- migration of existing rows doesn't break):
--
--   companion_mode='professional'   → mood ignored entirely (default, stable AI)
--   companion_mode='friendly'       → mood ignored entirely
--   companion_mode='affectionate'   → mood ignored entirely
--   companion_mode='partner' +
--     mood_realism='dynamic'         → mood state actively drives behavior
--       + repair_gate_enabled=true   → AI may stay distant when "hurt"
--
-- Run AFTER schema_phase3.sql exists. Idempotent.
-- =============================================================================


-- =============================================================================
-- 1. Stable companion preferences
-- =============================================================================

create table if not exists companion_settings (
    user_id uuid primary key references auth.users(id) on delete cascade,

    -- Companion behavior mode. User-facing choice.
    -- Default = professional. Aliyya-style behavior requires explicit 'partner'.
    companion_mode text not null default 'professional'
        check (companion_mode in ('professional', 'friendly', 'affectionate', 'partner')),

    -- Display name. Used in greetings, signed-off-by, prompt identity.
    assistant_name text not null default 'Assistant',

    -- Whether AI has dynamic moods that shift, or is emotionally consistent.
    -- App layer enforces: 'dynamic' only allowed when companion_mode='partner'.
    mood_realism text not null default 'stable'
        check (mood_realism in ('stable', 'dynamic')),

    -- Whether AI may stay distant ("ngambek") when hurt, requiring repair.
    -- App layer enforces: only when mood_realism='dynamic'.
    repair_gate_enabled boolean not null default false,

    -- Free-shape future fields. Saves migrations for things like:
    --   { "nickname": "beb", "communication_style": "casual", ... }
    preferences jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- We rely on app layer to filter by user_id (service-role pattern).
alter table companion_settings disable row level security;


-- =============================================================================
-- 2. Dynamic mood state — one row per user, TTL'd
--
-- Kept separate from settings because mood updates frequently (every emotion
-- trigger) and we want typed numeric columns for trend queries — not a single
-- jsonb blob.
--
-- TTL: mood naturally decays after 30 minutes of inactivity.
-- =============================================================================

create table if not exists companion_mood_state (
    user_id uuid primary key references auth.users(id) on delete cascade,

    -- Primary mood label. Source of truth for "which mood is dominant now".
    -- Free text (matches existing companion_mood_states.mood pattern).
    mood text not null default 'calm',

    -- 0-10 intensity. How strongly the mood is being felt.
    intensity integer not null default 1 check (intensity between 0 and 10),

    -- Russell circumplex axes (-1 to 1 typical, but we allow more).
    -- valence  = pleasant ↔ unpleasant
    -- arousal  = activated ↔ deactivated
    valence numeric not null default 0.35,
    arousal numeric not null default 0.2,

    -- Attachment / interpersonal axes (0-1).
    attachment numeric not null default 0.45,
    trust numeric not null default 0.6,
    insecurity numeric not null default 0.12,
    warmth numeric not null default 0.65,
    playfulness numeric not null default 0.35,

    -- Per-mood-state scores (which competing moods are pulling on the AI).
    -- Free shape so we can add new moods without migration.
    mood_scores jsonb not null default
        '{"calm":2,"hurt":0,"clingy":0,"annoyed":0,"focused":0,"playful":0,"romantic":0,"concerned":0,"reassured":0,"affectionate":0,"withdrawn_soft":0,"jealous_playful":0}'::jsonb,

    -- Audit / debugging fields.
    reason text default '',
    last_trigger text default '',
    source text default 'cold_start_default',
    version integer not null default 1,

    -- TTL: mood decays naturally after 30 min of no updates.
    -- App checks `expires_at < now()` and resets to calm if expired.
    expires_at timestamptz not null default (now() + interval '30 minutes'),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table companion_mood_state disable row level security;

create index if not exists companion_mood_state_expires_idx
    on companion_mood_state (expires_at);
