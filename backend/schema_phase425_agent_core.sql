-- =============================================================================
-- Phase 425 — Agent Core v1
--
-- Durable operational work state:
--   objective -> versioned plan -> plan steps -> append-only events
--
-- This migration deliberately does NOT repurpose:
--   memories
--   goals
--   calendar_pending_actions
--   proactive_nudges
--
-- External action execution is outside Agent Core v1.
-- =============================================================================

begin;

create table if not exists public.agent_objectives (
    id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references auth.users(id) on delete cascade,

    title text not null,
    desired_outcome text not null,

    status text not null default 'active'
        check (
            status in (
                'proposed',
                'active',
                'waiting',
                'paused',
                'completed',
                'cancelled'
            )
        ),

    priority text not null default 'normal'
        check (
            priority in (
                'low',
                'normal',
                'high'
            )
        ),

    goal_id uuid
        references public.goals(id) on delete set null,

    source_conversation_id uuid
        references public.conversations(id) on delete set null,

    source_message_id uuid
        references public.messages(id) on delete set null,

    creation_authority text not null
        check (
            creation_authority in (
                'explicit_user_request',
                'user_confirmed_proposal'
            )
        ),

    active_plan_id uuid,

    waiting_reason text,
    resume_after timestamptz,

    last_progress_at timestamptz,
    completed_at timestamptz,
    cancelled_at timestamptz,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    check (
        char_length(trim(title)) between 1 and 200
    ),

    check (
        char_length(trim(desired_outcome))
        between 1 and 5000
    )
);

create table if not exists public.agent_plans (
    id uuid primary key default gen_random_uuid(),

    objective_id uuid not null
        references public.agent_objectives(id)
        on delete cascade,

    user_id uuid not null
        references auth.users(id)
        on delete cascade,

    version integer not null
        check (version >= 1),

    status text not null default 'active'
        check (
            status in (
                'active',
                'completed',
                'superseded',
                'cancelled'
            )
        ),

    planning_reason text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    unique (objective_id, version)
);

alter table public.agent_objectives
    drop constraint if exists
        agent_objectives_active_plan_id_fkey;

alter table public.agent_objectives
    add constraint agent_objectives_active_plan_id_fkey
    foreign key (active_plan_id)
    references public.agent_plans(id)
    on delete set null;

create table if not exists public.agent_plan_steps (
    id uuid primary key default gen_random_uuid(),

    plan_id uuid not null
        references public.agent_plans(id)
        on delete cascade,

    objective_id uuid not null
        references public.agent_objectives(id)
        on delete cascade,

    user_id uuid not null
        references auth.users(id)
        on delete cascade,

    sequence integer not null
        check (sequence >= 1),

    title text not null,
    description text,

    step_kind text not null default 'internal'
        check (
            step_kind in (
                'internal',
                'user_input',
                'wait_time',
                'observe',
                'verify',
                'external_action'
            )
        ),

    status text not null default 'pending'
        check (
            status in (
                'pending',
                'ready',
                'in_progress',
                'waiting',
                'blocked',
                'completed',
                'failed',
                'cancelled'
            )
        ),

    requires_verification boolean
        not null default false,

    verification_status text
        not null default 'not_required'
        check (
            verification_status in (
                'not_required',
                'pending',
                'verified',
                'failed'
            )
        ),

    waiting_reason text,
    resume_after timestamptz,

    started_at timestamptz,
    completed_at timestamptz,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    unique (plan_id, sequence),

    check (
        char_length(trim(title)) between 1 and 200
    ),

    check (
        description is null
        or char_length(description) <= 2000
    )
);

create table if not exists public.agent_events (
    id uuid primary key default gen_random_uuid(),

    user_id uuid not null
        references auth.users(id)
        on delete cascade,

    objective_id uuid not null
        references public.agent_objectives(id)
        on delete cascade,

    plan_id uuid
        references public.agent_plans(id)
        on delete set null,

    step_id uuid
        references public.agent_plan_steps(id)
        on delete set null,

    event_type text not null
        check (
            event_type in (
                'objective_created',
                'objective_activated',
                'plan_created',
                'plan_superseded',
                'step_ready',
                'step_started',
                'observation',
                'verification',
                'step_completed',
                'step_failed',
                'objective_waiting',
                'objective_resumed',
                'objective_completed',
                'objective_cancelled',
                'note'
            )
        ),

    actor text not null
        check (
            actor in (
                'user',
                'assistant',
                'system'
            )
        ),

    evidence jsonb not null default '{}'::jsonb,

    source_conversation_id uuid
        references public.conversations(id)
        on delete set null,

    source_message_id uuid
        references public.messages(id)
        on delete set null,

    created_at timestamptz not null default now()
);

create index if not exists
    agent_objectives_user_status_updated_idx
on public.agent_objectives (
    user_id,
    status,
    updated_at desc
);

create index if not exists
    agent_objectives_resume_idx
on public.agent_objectives (
    user_id,
    resume_after
)
where status = 'waiting';

create unique index if not exists
    agent_objectives_source_message_unique_idx
on public.agent_objectives (source_message_id)
where source_message_id is not null;

create unique index if not exists
    agent_plans_one_active_per_objective_idx
on public.agent_plans (objective_id)
where status = 'active';

create index if not exists
    agent_plan_steps_objective_status_sequence_idx
on public.agent_plan_steps (
    objective_id,
    status,
    sequence
);

create index if not exists
    agent_plan_steps_user_status_updated_idx
on public.agent_plan_steps (
    user_id,
    status,
    updated_at desc
);

create index if not exists
    agent_events_objective_created_idx
on public.agent_events (
    objective_id,
    created_at desc
);

create index if not exists
    agent_events_user_created_idx
on public.agent_events (
    user_id,
    created_at desc
);

alter table public.agent_objectives
    enable row level security;

alter table public.agent_plans
    enable row level security;

alter table public.agent_plan_steps
    enable row level security;

alter table public.agent_events
    enable row level security;

drop policy if exists
    agent_objectives_select_own
on public.agent_objectives;

create policy agent_objectives_select_own
on public.agent_objectives
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists
    agent_plans_select_own
on public.agent_plans;

create policy agent_plans_select_own
on public.agent_plans
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists
    agent_plan_steps_select_own
on public.agent_plan_steps;

create policy agent_plan_steps_select_own
on public.agent_plan_steps
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists
    agent_events_select_own
on public.agent_events;

create policy agent_events_select_own
on public.agent_events
for select
to authenticated
using (auth.uid() = user_id);

revoke all on public.agent_objectives
from anon, authenticated;

revoke all on public.agent_plans
from anon, authenticated;

revoke all on public.agent_plan_steps
from anon, authenticated;

revoke all on public.agent_events
from anon, authenticated;

grant select on public.agent_objectives
to authenticated;

grant select on public.agent_plans
to authenticated;

grant select on public.agent_plan_steps
to authenticated;

grant select on public.agent_events
to authenticated;

grant all on public.agent_objectives
to service_role;

grant all on public.agent_plans
to service_role;

grant all on public.agent_plan_steps
to service_role;

grant all on public.agent_events
to service_role;


create or replace function
public.agent_core_create_objective_v1(
    p_user_id uuid,
    p_title text,
    p_desired_outcome text,
    p_creation_authority text,
    p_steps jsonb,
    p_priority text default 'normal',
    p_goal_id uuid default null,
    p_source_conversation_id uuid default null,
    p_source_message_id uuid default null
)
returns jsonb
language plpgsql
security invoker
as $$
declare
    v_objective_id uuid;
    v_plan_id uuid;
    v_step jsonb;
    v_sequence integer := 0;
    v_step_kind text;
    v_step_title text;
    v_step_description text;
    v_requires_verification boolean;
    v_step_id uuid;
begin
    if p_creation_authority not in (
        'explicit_user_request',
        'user_confirmed_proposal'
    ) then
        raise exception
            'invalid Agent Core creation authority';
    end if;

    if p_priority not in (
        'low',
        'normal',
        'high'
    ) then
        raise exception
            'invalid Agent Core priority';
    end if;

    if p_title is null
       or char_length(trim(p_title)) not between 1 and 200
    then
        raise exception
            'invalid Agent Core title';
    end if;

    if p_desired_outcome is null
       or char_length(trim(p_desired_outcome))
            not between 1 and 5000
    then
        raise exception
            'invalid Agent Core desired outcome';
    end if;

    if jsonb_typeof(p_steps) <> 'array'
       or jsonb_array_length(p_steps) < 1
       or jsonb_array_length(p_steps) > 20
    then
        raise exception
            'Agent Core plan requires 1-20 steps';
    end if;

    if p_goal_id is not null
       and not exists (
            select 1
            from public.goals g
            where g.id = p_goal_id
              and g.user_id = p_user_id
       )
    then
        raise exception
            'Agent Core goal does not belong to user';
    end if;

    if p_source_conversation_id is not null
       and not exists (
            select 1
            from public.conversations c
            where c.id = p_source_conversation_id
              and c.user_id = p_user_id
       )
    then
        raise exception
            'Agent Core source conversation does not belong to user';
    end if;

    if p_source_message_id is not null
       and not exists (
            select 1
            from public.messages m
            join public.conversations c
              on c.id = m.conversation_id
            where m.id = p_source_message_id
              and c.user_id = p_user_id
              and (
                    p_source_conversation_id is null
                    or m.conversation_id = p_source_conversation_id
              )
       )
    then
        raise exception
            'Agent Core source message does not belong to user';
    end if;

    insert into public.agent_objectives (
        user_id,
        title,
        desired_outcome,
        status,
        priority,
        goal_id,
        source_conversation_id,
        source_message_id,
        creation_authority,
        last_progress_at
    )
    values (
        p_user_id,
        trim(p_title),
        trim(p_desired_outcome),
        'active',
        p_priority,
        p_goal_id,
        p_source_conversation_id,
        p_source_message_id,
        p_creation_authority,
        now()
    )
    returning id
    into v_objective_id;

    insert into public.agent_plans (
        objective_id,
        user_id,
        version,
        status,
        planning_reason
    )
    values (
        v_objective_id,
        p_user_id,
        1,
        'active',
        'initial_objective_plan'
    )
    returning id
    into v_plan_id;

    update public.agent_objectives
    set
        active_plan_id = v_plan_id,
        updated_at = now()
    where id = v_objective_id
      and user_id = p_user_id;

    insert into public.agent_events (
        user_id,
        objective_id,
        plan_id,
        event_type,
        actor,
        evidence,
        source_conversation_id,
        source_message_id
    )
    values
    (
        p_user_id,
        v_objective_id,
        v_plan_id,
        'objective_created',
        'user',
        jsonb_build_object(
            'creation_authority',
            p_creation_authority
        ),
        p_source_conversation_id,
        p_source_message_id
    ),
    (
        p_user_id,
        v_objective_id,
        v_plan_id,
        'objective_activated',
        'user',
        jsonb_build_object(
            'creation_authority',
            p_creation_authority
        ),
        p_source_conversation_id,
        p_source_message_id
    ),
    (
        p_user_id,
        v_objective_id,
        v_plan_id,
        'plan_created',
        'assistant',
        jsonb_build_object(
            'version',
            1
        ),
        p_source_conversation_id,
        p_source_message_id
    );

    for v_step in
        select value
        from jsonb_array_elements(p_steps)
    loop
        v_sequence := v_sequence + 1;

        v_step_title := trim(
            coalesce(
                v_step ->> 'title',
                ''
            )
        );

        v_step_description := nullif(
            trim(
                coalesce(
                    v_step ->> 'description',
                    ''
                )
            ),
            ''
        );

        v_step_kind := coalesce(
            nullif(
                trim(
                    v_step ->> 'step_kind'
                ),
                ''
            ),
            'internal'
        );

        v_requires_verification := coalesce(
            (
                v_step
                ->> 'requires_verification'
            )::boolean,
            false
        );

        if char_length(v_step_title)
            not between 1 and 200
        then
            raise exception
                'invalid Agent Core step title';
        end if;

        if v_step_description is not null
           and char_length(v_step_description) > 2000
        then
            raise exception
                'Agent Core step description too long';
        end if;

        if v_step_kind not in (
            'internal',
            'user_input',
            'wait_time',
            'observe',
            'verify',
            'external_action'
        ) then
            raise exception
                'invalid Agent Core step kind';
        end if;

        insert into public.agent_plan_steps (
            plan_id,
            objective_id,
            user_id,
            sequence,
            title,
            description,
            step_kind,
            status,
            requires_verification,
            verification_status
        )
        values (
            v_plan_id,
            v_objective_id,
            p_user_id,
            v_sequence,
            v_step_title,
            v_step_description,
            v_step_kind,
            case
                when v_sequence = 1
                    then 'ready'
                else 'pending'
            end,
            v_requires_verification,
            case
                when v_requires_verification
                    then 'pending'
                else 'not_required'
            end
        )
        returning id
        into v_step_id;

        if v_sequence = 1 then
            insert into public.agent_events (
                user_id,
                objective_id,
                plan_id,
                step_id,
                event_type,
                actor,
                evidence,
                source_conversation_id,
                source_message_id
            )
            values (
                p_user_id,
                v_objective_id,
                v_plan_id,
                v_step_id,
                'step_ready',
                'system',
                jsonb_build_object(
                    'sequence',
                    v_sequence
                ),
                p_source_conversation_id,
                p_source_message_id
            );
        end if;
    end loop;

    return jsonb_build_object(
        'objective_id',
        v_objective_id,
        'plan_id',
        v_plan_id,
        'status',
        'active',
        'step_count',
        v_sequence
    );
end;
$$;


create or replace function
public.agent_core_transition_objective_v1(
    p_user_id uuid,
    p_objective_id uuid,
    p_to_status text,
    p_actor text default 'user',
    p_reason text default null,
    p_evidence jsonb default '{}'::jsonb,
    p_resume_after timestamptz default null
)
returns jsonb
language plpgsql
security invoker
as $$
declare
    v_from_status text;
    v_plan_id uuid;
    v_event_type text;
begin
    if p_actor not in (
        'user',
        'assistant',
        'system'
    ) then
        raise exception
            'invalid Agent Core actor';
    end if;

    select
        status,
        active_plan_id
    into
        v_from_status,
        v_plan_id
    from public.agent_objectives
    where id = p_objective_id
      and user_id = p_user_id
    for update;

    if not found then
        raise exception
            'Agent Core objective not found';
    end if;

    if not (
        (v_from_status = 'proposed'
            and p_to_status = 'active')
        or
        (v_from_status = 'active'
            and p_to_status in (
                'waiting',
                'paused',
                'completed',
                'cancelled'
            ))
        or
        (v_from_status = 'waiting'
            and p_to_status in (
                'active',
                'completed',
                'cancelled'
            ))
        or
        (v_from_status = 'paused'
            and p_to_status in (
                'active',
                'cancelled'
            ))
    ) then
        raise exception
            'invalid objective transition: % -> %',
            v_from_status,
            p_to_status;
    end if;

    if p_to_status = 'completed' then
        if v_plan_id is null then
            raise exception
                'objective has no active plan';
        end if;

        if exists (
            select 1
            from public.agent_plan_steps s
            where s.plan_id = v_plan_id
              and s.user_id = p_user_id
              and s.status <> 'completed'
        ) then
            raise exception
                'objective has incomplete plan steps';
        end if;

        if exists (
            select 1
            from public.agent_plan_steps s
            where s.plan_id = v_plan_id
              and s.user_id = p_user_id
              and s.requires_verification = true
              and s.verification_status <> 'verified'
        ) then
            raise exception
                'objective has unverified required steps';
        end if;
    end if;

    update public.agent_objectives
    set
        status = p_to_status,
        waiting_reason = case
            when p_to_status = 'waiting'
                then nullif(trim(p_reason), '')
            else null
        end,
        resume_after = case
            when p_to_status = 'waiting'
                then p_resume_after
            else null
        end,
        completed_at = case
            when p_to_status = 'completed'
                then now()
            else completed_at
        end,
        cancelled_at = case
            when p_to_status = 'cancelled'
                then now()
            else cancelled_at
        end,
        last_progress_at = now(),
        updated_at = now()
    where id = p_objective_id
      and user_id = p_user_id;

    if p_to_status = 'completed'
       and v_plan_id is not null
    then
        update public.agent_plans
        set
            status = 'completed',
            updated_at = now()
        where id = v_plan_id
          and user_id = p_user_id
          and status = 'active';
    end if;

    if p_to_status = 'cancelled'
       and v_plan_id is not null
    then
        update public.agent_plans
        set
            status = 'cancelled',
            updated_at = now()
        where id = v_plan_id
          and user_id = p_user_id
          and status = 'active';

        update public.agent_plan_steps
        set
            status = 'cancelled',
            updated_at = now()
        where plan_id = v_plan_id
          and user_id = p_user_id
          and status not in (
              'completed',
              'cancelled'
          );
    end if;

    v_event_type := case
        when p_to_status = 'waiting'
            then 'objective_waiting'
        when p_to_status = 'completed'
            then 'objective_completed'
        when p_to_status = 'cancelled'
            then 'objective_cancelled'
        when p_to_status = 'active'
            then case
                when v_from_status = 'proposed'
                    then 'objective_activated'
                else 'objective_resumed'
            end
        else 'note'
    end;

    insert into public.agent_events (
        user_id,
        objective_id,
        plan_id,
        event_type,
        actor,
        evidence
    )
    values (
        p_user_id,
        p_objective_id,
        v_plan_id,
        v_event_type,
        p_actor,
        coalesce(
            p_evidence,
            '{}'::jsonb
        )
        || jsonb_build_object(
            'from_status',
            v_from_status,
            'to_status',
            p_to_status,
            'reason',
            p_reason
        )
    );

    return jsonb_build_object(
        'objective_id',
        p_objective_id,
        'from_status',
        v_from_status,
        'status',
        p_to_status
    );
end;
$$;


create or replace function
public.agent_core_transition_step_v1(
    p_user_id uuid,
    p_step_id uuid,
    p_to_status text,
    p_actor text default 'user',
    p_reason text default null,
    p_evidence jsonb default '{}'::jsonb,
    p_resume_after timestamptz default null
)
returns jsonb
language plpgsql
security invoker
as $$
declare
    v_from_status text;
    v_objective_id uuid;
    v_plan_id uuid;
    v_requires_verification boolean;
    v_objective_status text;
    v_event_type text;
begin
    if p_actor not in (
        'user',
        'assistant',
        'system'
    ) then
        raise exception
            'invalid Agent Core actor';
    end if;

    select
        s.status,
        s.objective_id,
        s.plan_id,
        s.requires_verification,
        o.status
    into
        v_from_status,
        v_objective_id,
        v_plan_id,
        v_requires_verification,
        v_objective_status
    from public.agent_plan_steps s
    join public.agent_objectives o
      on o.id = s.objective_id
    where s.id = p_step_id
      and s.user_id = p_user_id
      and o.user_id = p_user_id
    for update of s, o;

    if not found then
        raise exception
            'Agent Core step not found';
    end if;

    if v_objective_status not in (
        'active',
        'waiting'
    ) then
        raise exception
            'objective is not executable in status %',
            v_objective_status;
    end if;

    if not (
        (v_from_status = 'pending'
            and p_to_status = 'ready')
        or
        (v_from_status = 'ready'
            and p_to_status in (
                'in_progress',
                'waiting',
                'blocked',
                'cancelled'
            ))
        or
        (v_from_status = 'in_progress'
            and p_to_status in (
                'completed',
                'waiting',
                'blocked',
                'failed'
            ))
        or
        (v_from_status = 'waiting'
            and p_to_status = 'ready')
        or
        (v_from_status = 'blocked'
            and p_to_status = 'ready')
        or
        (v_from_status = 'failed'
            and p_to_status in (
                'ready',
                'cancelled'
            ))
    ) then
        raise exception
            'invalid step transition: % -> %',
            v_from_status,
            p_to_status;
    end if;

    update public.agent_plan_steps
    set
        status = p_to_status,

        waiting_reason = case
            when p_to_status in (
                'waiting',
                'blocked'
            )
                then nullif(trim(p_reason), '')
            else null
        end,

        resume_after = case
            when p_to_status = 'waiting'
                then p_resume_after
            else null
        end,

        started_at = case
            when p_to_status = 'in_progress'
                 and started_at is null
                then now()
            else started_at
        end,

        completed_at = case
            when p_to_status = 'completed'
                then now()
            else completed_at
        end,

        verification_status = case
            when p_to_status = 'completed'
                 and v_requires_verification
                then 'pending'
            when p_to_status = 'completed'
                then 'not_required'
            else verification_status
        end,

        updated_at = now()

    where id = p_step_id
      and user_id = p_user_id;

    update public.agent_objectives
    set
        last_progress_at = now(),
        updated_at = now()
    where id = v_objective_id
      and user_id = p_user_id;

    v_event_type := case
        when p_to_status = 'ready'
            then 'step_ready'
        when p_to_status = 'in_progress'
            then 'step_started'
        when p_to_status = 'completed'
            then 'step_completed'
        when p_to_status = 'failed'
            then 'step_failed'
        else 'note'
    end;

    insert into public.agent_events (
        user_id,
        objective_id,
        plan_id,
        step_id,
        event_type,
        actor,
        evidence
    )
    values (
        p_user_id,
        v_objective_id,
        v_plan_id,
        p_step_id,
        v_event_type,
        p_actor,
        coalesce(
            p_evidence,
            '{}'::jsonb
        )
        || jsonb_build_object(
            'from_status',
            v_from_status,
            'to_status',
            p_to_status,
            'reason',
            p_reason
        )
    );

    return jsonb_build_object(
        'step_id',
        p_step_id,
        'objective_id',
        v_objective_id,
        'from_status',
        v_from_status,
        'status',
        p_to_status
    );
end;
$$;


create or replace function
public.agent_core_verify_step_v1(
    p_user_id uuid,
    p_step_id uuid,
    p_verification_status text,
    p_actor text default 'user',
    p_evidence jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security invoker
as $$
declare
    v_objective_id uuid;
    v_plan_id uuid;
    v_step_status text;
    v_requires_verification boolean;
begin
    if p_actor not in (
        'user',
        'assistant',
        'system'
    ) then
        raise exception
            'invalid Agent Core actor';
    end if;

    if p_verification_status not in (
        'verified',
        'failed'
    ) then
        raise exception
            'invalid verification status';
    end if;

    select
        objective_id,
        plan_id,
        status,
        requires_verification
    into
        v_objective_id,
        v_plan_id,
        v_step_status,
        v_requires_verification
    from public.agent_plan_steps
    where id = p_step_id
      and user_id = p_user_id
    for update;

    if not found then
        raise exception
            'Agent Core step not found';
    end if;

    if v_step_status <> 'completed' then
        raise exception
            'only completed steps may be verified';
    end if;

    if not v_requires_verification then
        raise exception
            'step does not require verification';
    end if;

    update public.agent_plan_steps
    set
        verification_status = p_verification_status,
        updated_at = now()
    where id = p_step_id
      and user_id = p_user_id;

    update public.agent_objectives
    set
        last_progress_at = now(),
        updated_at = now()
    where id = v_objective_id
      and user_id = p_user_id;

    insert into public.agent_events (
        user_id,
        objective_id,
        plan_id,
        step_id,
        event_type,
        actor,
        evidence
    )
    values (
        p_user_id,
        v_objective_id,
        v_plan_id,
        p_step_id,
        'verification',
        p_actor,
        coalesce(
            p_evidence,
            '{}'::jsonb
        )
        || jsonb_build_object(
            'verification_status',
            p_verification_status
        )
    );

    return jsonb_build_object(
        'step_id',
        p_step_id,
        'objective_id',
        v_objective_id,
        'verification_status',
        p_verification_status
    );
end;
$$;


create or replace function
public.agent_core_record_event_v1(
    p_user_id uuid,
    p_objective_id uuid,
    p_event_type text,
    p_actor text,
    p_evidence jsonb default '{}'::jsonb,
    p_plan_id uuid default null,
    p_step_id uuid default null,
    p_source_conversation_id uuid default null,
    p_source_message_id uuid default null
)
returns jsonb
language plpgsql
security invoker
as $$
declare
    v_event_id uuid;
begin
    if p_event_type not in (
        'observation',
        'note'
    ) then
        raise exception
            'event type not writable through generic event API';
    end if;

    if p_actor not in (
        'user',
        'assistant',
        'system'
    ) then
        raise exception
            'invalid Agent Core actor';
    end if;

    if not exists (
        select 1
        from public.agent_objectives
        where id = p_objective_id
          and user_id = p_user_id
    ) then
        raise exception
            'Agent Core objective not found';
    end if;

    if p_plan_id is not null
       and not exists (
            select 1
            from public.agent_plans
            where id = p_plan_id
              and objective_id = p_objective_id
              and user_id = p_user_id
       )
    then
        raise exception
            'Agent Core plan does not belong to objective';
    end if;

    if p_step_id is not null
       and not exists (
            select 1
            from public.agent_plan_steps
            where id = p_step_id
              and objective_id = p_objective_id
              and user_id = p_user_id
       )
    then
        raise exception
            'Agent Core step does not belong to objective';
    end if;

    insert into public.agent_events (
        user_id,
        objective_id,
        plan_id,
        step_id,
        event_type,
        actor,
        evidence,
        source_conversation_id,
        source_message_id
    )
    values (
        p_user_id,
        p_objective_id,
        p_plan_id,
        p_step_id,
        p_event_type,
        p_actor,
        coalesce(
            p_evidence,
            '{}'::jsonb
        ),
        p_source_conversation_id,
        p_source_message_id
    )
    returning id
    into v_event_id;

    update public.agent_objectives
    set
        last_progress_at = now(),
        updated_at = now()
    where id = p_objective_id
      and user_id = p_user_id;

    return jsonb_build_object(
        'event_id',
        v_event_id,
        'objective_id',
        p_objective_id,
        'event_type',
        p_event_type
    );
end;
$$;


revoke all on function
public.agent_core_create_objective_v1(
    uuid,
    text,
    text,
    text,
    jsonb,
    text,
    uuid,
    uuid,
    uuid
)
from public, anon, authenticated;

grant execute on function
public.agent_core_create_objective_v1(
    uuid,
    text,
    text,
    text,
    jsonb,
    text,
    uuid,
    uuid,
    uuid
)
to service_role;


revoke all on function
public.agent_core_transition_objective_v1(
    uuid,
    uuid,
    text,
    text,
    text,
    jsonb,
    timestamptz
)
from public, anon, authenticated;

grant execute on function
public.agent_core_transition_objective_v1(
    uuid,
    uuid,
    text,
    text,
    text,
    jsonb,
    timestamptz
)
to service_role;


revoke all on function
public.agent_core_transition_step_v1(
    uuid,
    uuid,
    text,
    text,
    text,
    jsonb,
    timestamptz
)
from public, anon, authenticated;

grant execute on function
public.agent_core_transition_step_v1(
    uuid,
    uuid,
    text,
    text,
    text,
    jsonb,
    timestamptz
)
to service_role;


revoke all on function
public.agent_core_verify_step_v1(
    uuid,
    uuid,
    text,
    text,
    jsonb
)
from public, anon, authenticated;

grant execute on function
public.agent_core_verify_step_v1(
    uuid,
    uuid,
    text,
    text,
    jsonb
)
to service_role;


revoke all on function
public.agent_core_record_event_v1(
    uuid,
    uuid,
    text,
    text,
    jsonb,
    uuid,
    uuid,
    uuid,
    uuid
)
from public, anon, authenticated;

grant execute on function
public.agent_core_record_event_v1(
    uuid,
    uuid,
    text,
    text,
    jsonb,
    uuid,
    uuid,
    uuid,
    uuid
)
to service_role;

notify pgrst, 'reload schema';

commit;
