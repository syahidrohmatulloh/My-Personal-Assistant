-- =============================================================================
-- M35c2a — Stop-the-Bleeding Epistemic Write Contract
--
-- Purpose:
--   Prevent new memory rows from receiving a synthetic confirmation timestamp.
--
-- Historical rows are intentionally untouched. Historical cleanup belongs to
-- M35c2b after the future-write contract is proven safe in production.
--
-- Invariant:
--   insertion != confirmation
--   repetition != confirmation
--   inference != confirmation
--
-- This migration changes column metadata only:
--   last_confirmed_at DEFAULT now() -> no default
--
-- No INSERT / UPDATE / DELETE / backfill.
-- =============================================================================

begin;

alter table public.memories
    alter column last_confirmed_at drop default;

notify pgrst, 'reload schema';

commit;
