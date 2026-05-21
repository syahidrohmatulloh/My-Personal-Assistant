-- Phase 4.18F — Memory Hygiene Gate
-- Database-level last line of defense against trivial accidental memories.
--
-- Safe/idempotent:
-- - Replaces function/trigger.
-- - Does not delete existing memories.
-- - Skips only universal low-value fragments before insert.

create or replace function public.memory_hygiene_should_skip_insert(
    p_content text,
    p_structured_field text,
    p_structured_value text,
    p_source text
)
returns boolean
language plpgsql
as $$
declare
    cleaned text;
    token_count integer;
begin
    cleaned := lower(trim(coalesce(p_content, '')));

    if cleaned = '' then
        return true;
    end if;

    cleaned := regexp_replace(cleaned, '[[:space:]]+', ' ', 'g');
    cleaned := regexp_replace(cleaned, '[!?.。！？]+$', '', 'g');

    if cleaned in (
        'hi', 'hai', 'hey', 'hello', 'halo', 'hallo',
        'pagi', 'siang', 'sore', 'malam',
        'ok', 'oke', 'okay', 'sip', 'siap',
        'yes', 'no', 'ya', 'iya', 'y',
        'done', 'lanjut', 'next',
        'test', 'testing', 'coba', 'tes',
        'makasih', 'thanks', 'thank you', 'noted'
    ) then
        return true;
    end if;

    if cleaned ~ '^[^[:alnum:]]+$' then
        return true;
    end if;

    token_count := array_length(regexp_split_to_array(cleaned, '[[:space:]]+'), 1);

    if token_count <= 1
       and nullif(trim(coalesce(p_structured_field, '')), '') is null
       and nullif(trim(coalesce(p_structured_value, '')), '') is null then
        return true;
    end if;

    if token_count <= 2
       and nullif(trim(coalesce(p_structured_field, '')), '') is null
       and nullif(trim(coalesce(p_structured_value, '')), '') is null
       and cleaned !~ '[0-9@:/+\-]'
       and cleaned !~ '\m(gmt|utc|wib|wita|wit)\M' then
        return true;
    end if;

    return false;
end;
$$;

create or replace function public.memories_hygiene_before_insert()
returns trigger
language plpgsql
as $$
begin
    if public.memory_hygiene_should_skip_insert(
        new.content,
        new.structured_field,
        new.structured_value,
        new.source
    ) then
        return null;
    end if;

    if new.updated_at is null then
        new.updated_at := coalesce(new.created_at, now());
    end if;

    return new;
end;
$$;

drop trigger if exists memories_hygiene_before_insert on public.memories;

create trigger memories_hygiene_before_insert
before insert on public.memories
for each row
execute function public.memories_hygiene_before_insert();

notify pgrst, 'reload schema';
