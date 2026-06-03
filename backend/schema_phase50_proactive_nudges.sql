-- Phase 50 — Proactive in-chat reminders / nudges

create table if not exists proactive_nudges (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    conversation_id uuid not null references conversations(id) on delete cascade,
    status text not null default 'scheduled'
        check (status in ('scheduled', 'processing', 'sent', 'failed', 'cancelled')),
    due_at timestamptz not null,
    title text not null,
    message text not null,
    source_user_message text,
    delivered_message_id uuid references messages(id) on delete set null,
    delivered_at timestamptz,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists proactive_nudges_due_idx
    on proactive_nudges (status, due_at);

create index if not exists proactive_nudges_user_idx
    on proactive_nudges (user_id, created_at desc);

create index if not exists proactive_nudges_conversation_idx
    on proactive_nudges (conversation_id, created_at desc);

alter table proactive_nudges enable row level security;

drop policy if exists proactive_nudges_select_own on proactive_nudges;
create policy proactive_nudges_select_own
    on proactive_nudges
    for select
    using (auth.uid() = user_id);

notify pgrst, 'reload schema';
