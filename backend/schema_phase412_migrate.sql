-- =============================================================================
-- Phase 4.12 Migration — copy old state to new tables
--
-- Run AFTER schema_phase412_companion.sql.
-- Safe to re-run (idempotent via on conflict).
--
-- This DOES NOT drop the old tables. After confirming chat behavior is intact
-- in Zip 2, run schema_phase412_drop_old.sql separately to remove them.
-- =============================================================================


-- =============================================================================
-- 1. Migrate user_state → companion_settings.preferences
--
-- The user_state table held nickname / mode / communication_style fields
-- that ChatGPT created but never wired to chat.py. We preserve them in
-- preferences jsonb so nothing is lost, in case any field becomes useful later.
--
-- The 'mode' column from user_state is NOT mapped to companion_settings.companion_mode
-- because they meant different things — user_state.mode was free text, our
-- companion_mode is a controlled enum.
-- =============================================================================

insert into companion_settings (user_id, companion_mode, assistant_name, preferences)
select
    us.user_id,
    -- Existing users keep professional default. The Aliyya user gets escalated
    -- separately in step 3 below.
    'professional' as companion_mode,
    'Assistant' as assistant_name,
    -- Stash the old fields in preferences jsonb for inspection / future use.
    jsonb_strip_nulls(jsonb_build_object(
        'legacy_mode', us.mode,
        'legacy_romantic_baseline', us.romantic_baseline,
        'legacy_communication_style', us.communication_style,
        'legacy_nickname', us.nickname,
        'legacy_nickname_preference', us.nickname_preference
    )) as preferences
from user_state us
on conflict (user_id) do nothing;


-- =============================================================================
-- 2. Migrate companion_mood_states (global scope only) → companion_mood_state
--
-- Conversation-scoped mood states are dropped intentionally. Per audit
-- decision: one user has ONE mood at a time, not different moods per chat.
-- That was a split-personality bug.
-- =============================================================================

insert into companion_mood_state (
    user_id, mood, intensity, valence, arousal,
    attachment, trust, insecurity, warmth, playfulness,
    mood_scores, reason, last_trigger, source, version,
    expires_at, created_at, updated_at
)
select distinct on (user_id)
    user_id, mood, intensity, valence, arousal,
    attachment, trust, insecurity, warmth, playfulness,
    mood_scores, reason, last_trigger, source, version,
    expires_at, created_at, updated_at
from companion_mood_states
where scope = 'global'
order by user_id, updated_at desc
on conflict (user_id) do nothing;


-- =============================================================================
-- 3. Escalate existing Aliyya user (Syahid) to partner mode
--
-- The user with assistant_name='Aliyya' has been actively using companion mood
-- features. Per migration plan: keep their setup intact, just marked as opt-in.
--
-- This UPDATE matches the user who has any mood state in the migrated table.
-- If you want to limit it to specific users, change the WHERE clause.
--
-- Safe to re-run: only updates rows still in default state.
-- =============================================================================

update companion_settings cs
set
    companion_mode = 'partner',
    assistant_name = 'Aliyya',
    mood_realism = 'dynamic',
    repair_gate_enabled = true,
    updated_at = now()
where cs.user_id in (
    -- Anyone with an existing mood state row gets escalated. In practice
    -- right now that's just Syahid. New users will not match.
    select user_id from companion_mood_state
)
and cs.companion_mode = 'professional';  -- only if still default
