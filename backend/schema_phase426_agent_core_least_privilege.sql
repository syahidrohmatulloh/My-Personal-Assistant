-- =============================================================================
-- Phase 426 — Agent Core least-privilege hardening
--
-- Phase 425 established the durable Agent Core schema.
-- This migration narrows server-side table privileges:
--
--   agent_objectives  SELECT / INSERT / UPDATE
--   agent_plans       SELECT / INSERT / UPDATE
--   agent_plan_steps  SELECT / INSERT / UPDATE
--   agent_events      SELECT / INSERT only (append-only)
--
-- Browser-authenticated users remain read-only through RLS.
-- Agent Core mutation RPCs remain service_role-only.
-- =============================================================================

begin;

revoke all on public.agent_objectives
from anon, authenticated, service_role;

revoke all on public.agent_plans
from anon, authenticated, service_role;

revoke all on public.agent_plan_steps
from anon, authenticated, service_role;

revoke all on public.agent_events
from anon, authenticated, service_role;


grant select on public.agent_objectives
to authenticated;

grant select on public.agent_plans
to authenticated;

grant select on public.agent_plan_steps
to authenticated;

grant select on public.agent_events
to authenticated;


grant select, insert, update
on public.agent_objectives
to service_role;

grant select, insert, update
on public.agent_plans
to service_role;

grant select, insert, update
on public.agent_plan_steps
to service_role;

grant select, insert
on public.agent_events
to service_role;


notify pgrst, 'reload schema';

commit;
