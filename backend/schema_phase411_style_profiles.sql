-- =============================================================================
-- Phase 4.11: Conversation Style Profiles
--
-- Lets a user paste a chat transcript with someone, extract that person's
-- communication style, and start NEW conversations adopting that style.
-- The assistant never claims to be that person — adapts tone only.
--
-- Transcripts are NEVER stored. Only extracted style JSON survives. The
-- raw text is processed in memory by the analyze endpoint and discarded.
--
-- Run once in Supabase SQL Editor. Idempotent.
-- =============================================================================

create table if not exists style_profiles (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users(id) on delete cascade not null,

    profile_name text not null,

    -- 'whatsapp' | 'telegram' | 'plain' | 'pasted'
    -- 'pasted' = generic paste that we couldn't parse; treated as plain text.
    source_type text not null check (source_type in ('whatsapp', 'telegram', 'plain', 'pasted')),

    -- Full structured profile. Free-form jsonb so we can evolve the schema
    -- without migrations as the extractor improves.
    --
    -- Expected shape (enforced by Pydantic in the extractor service, NOT here):
    --   {
    --     "display_name": str,
    --     "dominant_language": str,
    --     "language_mixing": str,
    --     "formality_level": str,
    --     "warmth_level": str,
    --     "directness_level": str,
    --     "humor_style": str,
    --     "emoji_usage": str,
    --     "average_reply_length": str,
    --     "greeting_style": str,
    --     "closing_style": str,
    --     "conflict_style": str,
    --     "support_style": str,
    --     "decision_making_style": str,
    --     "common_phrases": [str],
    --     "do_not_copy": [str],
    --     "compact_directive": str
    --   }
    extracted_style jsonb not null,

    sample_count int not null default 0,   -- how many messages from target we analyzed
    confidence float check (confidence is null or (confidence >= 0 and confidence <= 1)),

    created_at timestamptz default now() not null,
    updated_at timestamptz default now() not null,

    unique (user_id, profile_name)
);

create index if not exists style_profiles_user_id_idx
    on style_profiles (user_id, updated_at desc);

-- Link a conversation to an optional style profile. When set, the chat router
-- injects the profile's compact_directive into the system prompt for that
-- conversation only. NULL = default behavior (current chat).
alter table conversations
    add column if not exists style_profile_id uuid
    references style_profiles(id) on delete set null;
