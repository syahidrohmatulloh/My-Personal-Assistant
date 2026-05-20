-- =============================================================================
-- Phase 416 — Goal action proposals
--
-- Pending, confirmable actions against existing goals.
-- This is intentionally separate from goal_suggestions:
-- - goal_suggestions creates new goals after confirmation
-- - goal_action_proposals modifies/deletes existing goals after confirmation
--
-- Destructive or modifying actions should be proposed first, then confirmed.
-- =============================================================================

create table if not exists goal_action_proposals (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users on delete cascade not null,
    goal_id uuid references goals(id) on delete cascade not null,

    action_type text not null check (action_type in (
        'mark_achieved',
        'pause',
        'resume',
        'abandon',
        'delete',
        'update'
    )),

    -- For action_type='update', store proposed field changes here.
    -- Example:
    -- {
    --   "title": "Turun berat badan ke 72 kg",
    --   "description": "...",
    --   "target_date": "2026-12-31",
    --   "clear_target_date": false
    -- }
    proposed_patch jsonb default '{}'::jsonb not null,

    assistant_reason text,
    confidence numeric default 0.7 check (confidence >= 0 and confidence <= 1),

    status text not null default 'pending' check (status in (
        'pending',
        'confirmed',
        'dismissed'
    )),

    confirmed_at timestamptz,
    dismissed_at timestamptz,
    created_at timestamptz default now() not null,
    updated_at timestamptz default now() not null
);

create index if not exists goal_action_proposals_user_status_idx
    on goal_action_proposals (user_id, status, created_at desc);

create index if not exists goal_action_proposals_goal_status_idx
    on goal_action_proposals (goal_id, status, created_at desc);

alter table goal_action_proposals enable row level security;

drop policy if exists "own goal action proposals" on goal_action_proposals;

create policy "own goal action proposals" on goal_action_proposals
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
