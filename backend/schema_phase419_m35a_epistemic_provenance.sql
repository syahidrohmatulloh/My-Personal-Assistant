-- M35a — Epistemic Honesty Hotfix
--
-- Extend source_priority with deterministic system-generated inference.
-- No historical backfill.
-- Safe to re-run: existing source_priority CHECK constraints are discovered
-- dynamically rather than assuming a constraint name.

begin;

do $$
declare
    constraint_row record;
begin
    for constraint_row in
        select c.conname
        from pg_constraint c
        join pg_class t
          on t.oid = c.conrelid
        join pg_namespace n
          on n.oid = t.relnamespace
        where n.nspname = 'public'
          and t.relname = 'memories'
          and c.contype = 'c'
          and pg_get_constraintdef(c.oid) ilike '%source_priority%'
    loop
        execute format(
            'alter table public.memories drop constraint %I',
            constraint_row.conname
        );
    end loop;
end
$$;

alter table public.memories
    add constraint memories_source_priority_check
    check (
        source_priority in (
            'explicit_user_statement',
            'user_answer_in_context',
            'user_correction',
            'repeated_pattern',
            'assistant_confirmation',
            'system_inference'
        )
    );

commit;
