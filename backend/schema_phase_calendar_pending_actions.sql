-- Durable continuation state for recurring Google Calendar actions.
-- Run this migration before deploying the backend code that uses it.

create table if not exists public.calendar_pending_actions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    conversation_id uuid not null
        references public.conversations(id) on delete cascade,

    action_type text not null
        check (action_type in ('update', 'delete')),
    target_source text not null default 'google'
        check (target_source in ('google')),

    google_event_id text not null,
    google_calendar_id text not null default 'primary',
    google_recurring_event_id text,

    target_snapshot jsonb not null default '{}'::jsonb,
    requested_action jsonb not null default '{}'::jsonb,

    status text not null default 'pending'
        check (
            status in (
                'pending',
                'completed',
                'cancelled',
                'expired'
            )
        ),

    expires_at timestamptz not null
        default (now() + interval '30 minutes'),
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists
    calendar_pending_actions_lookup_idx
on public.calendar_pending_actions (
    user_id,
    conversation_id,
    status,
    created_at desc
);

create index if not exists
    calendar_pending_actions_expiry_idx
on public.calendar_pending_actions (expires_at)
where status = 'pending';

create unique index if not exists
    calendar_pending_actions_one_pending_per_chat_idx
on public.calendar_pending_actions (
    user_id,
    conversation_id
)
where status = 'pending';

alter table public.calendar_pending_actions
    enable row level security;

drop policy if exists
    calendar_pending_actions_select_own
on public.calendar_pending_actions;

create policy calendar_pending_actions_select_own
on public.calendar_pending_actions
for select
using (auth.uid() = user_id);

drop policy if exists
    calendar_pending_actions_insert_own
on public.calendar_pending_actions;

create policy calendar_pending_actions_insert_own
on public.calendar_pending_actions
for insert
with check (auth.uid() = user_id);

drop policy if exists
    calendar_pending_actions_update_own
on public.calendar_pending_actions;

create policy calendar_pending_actions_update_own
on public.calendar_pending_actions
for update
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists
    calendar_pending_actions_delete_own
on public.calendar_pending_actions;

create policy calendar_pending_actions_delete_own
on public.calendar_pending_actions
for delete
using (auth.uid() = user_id);
