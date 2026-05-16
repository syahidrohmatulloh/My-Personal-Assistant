-- =============================================================================
-- Phase 4.10: Extend get_user_context() to surface
--   - up to 3 recent relationship notes per important person
--   - the latest check-in per active goal
--
-- Wraps current notes/check-ins inside the people/goals jsonb so the prompt
-- builder can render them inline without separate queries.
--
-- Idempotent — CREATE OR REPLACE.
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
                'id', g.id, 'title', g.title, 'horizon', g.horizon,
                'emotional_weight', g.emotional_weight,
                'target_date', g.target_date,
                'latest_check_in', (
                    select jsonb_build_object(
                        'momentum', momentum,
                        'note', note,
                        'created_at', created_at
                    )
                    from goal_check_ins
                    where goal_id = g.id
                    order by created_at desc
                    limit 1
                )
            ) order by g.emotional_weight desc), '[]'::jsonb)
            from goals g
            where g.user_id = p_user_id and g.status = 'active'
        ),
        'important_people', (
            select coalesce(jsonb_agg(jsonb_build_object(
                'id', p.id, 'name', p.name, 'relationship', p.relationship,
                'importance', p.importance,
                'emotional_significance', p.emotional_significance,
                'recent_notes', (
                    select coalesce(jsonb_agg(jsonb_build_object(
                        'content', n.content,
                        'kind', n.kind,
                        'created_at', n.created_at
                    ) order by n.created_at desc), '[]'::jsonb)
                    from (
                        select content, kind, created_at
                        from relationship_notes
                        where person_id = p.id
                          and superseded = false
                        order by created_at desc
                        limit 3
                    ) n
                )
            ) order by p.importance desc), '[]'::jsonb)
            from people p
            where p.user_id = p_user_id and p.importance >= 7
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
