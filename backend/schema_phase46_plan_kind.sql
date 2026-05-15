-- =============================================================================
-- Phase 4.6: Allow 'plan' as a memory kind.
--
-- "plan" entries capture concrete recommendations the assistant gave the user
-- (diet plan, workout plan, study plan, etc.) that the user accepted. These
-- need to survive across chats just like facts/preferences.
--
-- Idempotent — drops the old constraint if present, adds the new one.
-- =============================================================================

alter table memories drop constraint if exists memories_kind_check;
alter table memories
    add constraint memories_kind_check
    check (kind in ('fact', 'preference', 'context', 'plan'));
