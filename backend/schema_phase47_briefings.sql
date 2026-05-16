-- =============================================================================
-- Phase 4.7: Daily briefings.
--
-- One row per user per day. Generated when the user opens the app and there's
-- no row for today's date in their timezone (resolved client-side; the date
-- string is passed in by the API).
--
-- Briefings are NOT auto-generated on a schedule yet — that's Step 2. This
-- table just persists what gets generated on first open so we don't re-call
-- Haiku for every page load.
-- =============================================================================

create table if not exists daily_briefings (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,

    -- The local date this briefing represents (in user's timezone).
    -- Stored as text 'YYYY-MM-DD' rather than date type because the timezone
    -- context lives in the user's identity profile and we want exact match.
    briefing_date text not null,

    content text not null,
    generated_at timestamptz not null default now(),

    -- Reference to the conversation that was opened from this briefing, if any.
    -- Null until user taps the card.
    conversation_id uuid references conversations(id) on delete set null,
    opened_at timestamptz,

    -- One briefing per user per date.
    unique (user_id, briefing_date)
);

create index if not exists daily_briefings_user_date_idx
    on daily_briefings (user_id, briefing_date desc);

-- RLS: same pattern as other tables — backend uses service role, frontend
-- never queries this directly.
alter table daily_briefings enable row level security;
