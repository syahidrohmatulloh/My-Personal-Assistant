-- =============================================================================
-- Patch: fix get_user_context() self-reflections limit
--
-- The previous version had `limit 10` INSIDE `jsonb_agg(...)`, which Postgres
-- ignores — jsonb_agg aggregates whatever is in scope. We now wrap the limit
-- in a subquery so it actually applies.
--
-- Harmless to run multiple times — it's just a CREATE OR REPLACE.
-- Run AFTER schema_phase3.sql exists.
-- =============================================================================

create or replace function get_user_context(
    p_user_id uuid,
    p_mood_days int default 14
)
returns jsonb
language sql
stable
as $$
    select jsonb_build_object(
        'identity', (
            select jsonb_build_object(
                'profile', profile,
                'narrative', narrative,
                'updated_at', updated_at
            )
            from user_identity where user_id = p_user_id
        ),
        'recent_mood', (
            select coalesce(jsonb_agg(jsonb_build_object(
                'mood', mood, 'energy', energy, 'stress', stress,
                'dimensions', dimensions,
                'note', note, 'observed_at', observed_at,
                'source', source, 'confidence', confidence
            ) order by observed_at desc), '[]'::jsonb)
            from emotional_state
            where user_id = p_user_id
              and superseded = false
              and observed_at > now() - (p_mood_days || ' days')::interval
        ),
        'active_goals', (
            select coalesce(jsonb_agg(jsonb_build_object(
                'id', id, 'title', title, 'horizon', horizon,
                'emotional_weight', emotional_weight,
                'target_date', target_date
            ) order by emotional_weight desc), '[]'::jsonb)
            from goals
            where user_id = p_user_id and status = 'active'
        ),
        'important_people', (
            select coalesce(jsonb_agg(jsonb_build_object(
                'id', id, 'name', name, 'relationship', relationship,
                'importance', importance,
                'emotional_significance', emotional_significance
            ) order by importance desc), '[]'::jsonb)
            from people
            where user_id = p_user_id and importance >= 7
        ),
        'recent_events', (
            select coalesce(jsonb_agg(jsonb_build_object(
                'title', title, 'category', category,
                'happened_on', happened_on, 'significance', significance
            ) order by happened_on desc), '[]'::jsonb)
            from life_events
            where user_id = p_user_id
              and happened_on > now() - interval '90 days'
        ),
        'recent_self_reflections', (
            -- Wrap the LIMIT in a subquery so it actually applies before agg.
            select coalesce(jsonb_agg(jsonb_build_object(
                'content', content, 'kind', kind, 'created_at', created_at
            ) order by created_at desc), '[]'::jsonb)
            from (
                select content, kind, created_at
                from self_reflections
                where user_id = p_user_id
                  and created_at > now() - interval '60 days'
                order by created_at desc
                limit 10
            ) recent
        )
    );
$$;
