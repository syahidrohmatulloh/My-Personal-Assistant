-- =============================================================================
-- Phase 4.12 — Drop old tables
--
-- DO NOT RUN THIS UNTIL:
--   1. Zip 1 migration applied (companion_settings + companion_mood_state populated)
--   2. Zip 2 chat pipeline deployed and verified working
--   3. You've confirmed Aliyya behavior is intact in chat
--
-- This drops:
--   - user_state (orphan code, never wired to chat.py)
--   - companion_mood_states (replaced by companion_mood_state, singular)
--
-- Safe rollback: re-create from Supabase snapshot if needed.
-- =============================================================================

drop table if exists user_state cascade;
drop table if exists companion_mood_states cascade;
