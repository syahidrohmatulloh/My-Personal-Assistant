-- =============================================================================
-- Phase 4.15 — Memory hygiene + deterministic profile (Zip 6 v2)
--
-- Production-safe / multi-user revision:
-- 1. Drop & recreate `match_memories` RPC to filter superseded=false.
-- 2. Cleanup birthday duplicates per user → one canonical row per user.
-- 3. Normalize full birthday dates to ISO YYYY-MM-DD when a year is clearly known.
-- 4. Update user_identity.profile.birthday per user only from that user's own
--    canonical birthday evidence.
--
-- Safe to re-run. Does not delete rows; duplicates are marked superseded=true.
-- =============================================================================


-- =============================================================================
-- 0. Backward-compatible columns used by memory intelligence / hygiene
-- =============================================================================

alter table memories add column if not exists confidence real;
alter table memories add column if not exists source_priority text;
alter table memories add column if not exists evidence jsonb not null default '[]'::jsonb;
alter table memories add column if not exists category text;
alter table memories add column if not exists structured_field text;
alter table memories add column if not exists structured_value text;
alter table memories add column if not exists superseded boolean not null default false;
alter table memories add column if not exists superseded_by uuid;
alter table memories add column if not exists superseded_at timestamptz;
alter table memories add column if not exists last_confirmed_at timestamptz;

create index if not exists memories_user_structured_field_active_idx
    on memories (user_id, structured_field, created_at desc)
    where superseded = false and structured_field is not null;

create index if not exists memories_user_superseded_idx
    on memories (user_id, superseded, created_at desc);


-- =============================================================================
-- 1. New match_memories RPC with superseded filter
-- =============================================================================

drop function if exists match_memories(uuid, vector(1024), integer);

create or replace function match_memories(
    p_user_id uuid,
    p_query_embedding vector(1024),
    p_match_count integer
)
returns table (
    id uuid,
    content text,
    kind text,
    source text,
    source_conversation_id uuid,
    created_at timestamptz,
    similarity double precision,
    category text,
    confidence real,
    structured_field text,
    structured_value text,
    superseded boolean
)
language sql
stable
as $$
    select
        m.id,
        m.content,
        m.kind,
        m.source,
        m.source_conversation_id,
        m.created_at,
        1 - (m.embedding <=> p_query_embedding) as similarity,
        m.category,
        m.confidence::real as confidence,
        m.structured_field,
        m.structured_value,
        coalesce(m.superseded, false) as superseded
    from memories m
    where m.user_id = p_user_id
      and m.embedding is not null
      and coalesce(m.superseded, false) = false
    order by m.embedding <=> p_query_embedding
    limit p_match_count;
$$;


-- =============================================================================
-- 2. Helper functions for safe birthday normalization
--    Dropped at the end of this script. They are only migration helpers.
-- =============================================================================

create or replace function _phase415_month_num(month_text text)
returns int
language sql
immutable
as $$
    select case lower(month_text)
        when 'januari' then 1 when 'jan' then 1 when 'january' then 1
        when 'februari' then 2 when 'feb' then 2 when 'february' then 2
        when 'maret' then 3 when 'mar' then 3 when 'march' then 3
        when 'april' then 4 when 'apr' then 4
        when 'mei' then 5 when 'may' then 5
        when 'juni' then 6 when 'jun' then 6 when 'june' then 6
        when 'juli' then 7 when 'jul' then 7 when 'july' then 7
        when 'agustus' then 8 when 'agu' then 8 when 'aug' then 8 when 'august' then 8
        when 'september' then 9 when 'sep' then 9
        when 'oktober' then 10 when 'okt' then 10 when 'oct' then 10 when 'october' then 10
        when 'november' then 11 when 'nov' then 11
        when 'desember' then 12 when 'des' then 12 when 'dec' then 12 when 'december' then 12
        else null
    end;
$$;

create or replace function _phase415_parse_birthday_date(raw_value text)
returns date
language plpgsql
immutable
as $$
declare
    raw text;
    m text[];
    month_int int;
begin
    if raw_value is null or btrim(raw_value) = '' then
        return null;
    end if;

    raw := lower(regexp_replace(raw_value, ',', ' ', 'g'));

    -- ISO: 1995-01-07
    m := regexp_match(raw, '\m(\d{4})-(\d{2})-(\d{2})\M');
    if m is not null then
        begin
            return make_date(m[1]::int, m[2]::int, m[3]::int);
        exception when others then
            return null;
        end;
    end if;

    -- Indonesian / mixed: 7 Januari 1995, 7 January 1995
    m := regexp_match(raw, '\m(\d{1,2})\s+([a-z]+)\s+(\d{4})\M');
    if m is not null then
        month_int := _phase415_month_num(m[2]);
        if month_int is not null then
            begin
                return make_date(m[3]::int, month_int, m[1]::int);
            exception when others then
                return null;
            end;
        end if;
    end if;

    -- English: January 7 1995, January 7th 1995
    m := regexp_match(raw, '\m([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})\M');
    if m is not null then
        month_int := _phase415_month_num(m[1]);
        if month_int is not null then
            begin
                return make_date(m[3]::int, month_int, m[2]::int);
            exception when others then
                return null;
            end;
        end if;
    end if;

    return null;
end;
$$;

create or replace function _phase415_parse_birthday_month_day(raw_value text)
returns text
language plpgsql
immutable
as $$
declare
    raw text;
    m text[];
    month_int int;
    day_int int;
    fake_date date;
begin
    if raw_value is null or btrim(raw_value) = '' then
        return null;
    end if;

    raw := lower(regexp_replace(raw_value, ',', ' ', 'g'));

    -- Full date can also provide month/day.
    fake_date := _phase415_parse_birthday_date(raw_value);
    if fake_date is not null then
        return to_char(fake_date, 'FMMonth FMDD');
    end if;

    -- Indonesian / mixed without year: 7 Januari, 7 January
    m := regexp_match(raw, '\m(\d{1,2})\s+([a-z]+)\M');
    if m is not null then
        month_int := _phase415_month_num(m[2]);
        day_int := m[1]::int;
        if month_int is not null and day_int between 1 and 31 then
            return to_char(make_date(2000, month_int, day_int), 'FMMonth FMDD');
        end if;
    end if;

    -- English without year: January 7, January 7th
    m := regexp_match(raw, '\m([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\M');
    if m is not null then
        month_int := _phase415_month_num(m[1]);
        day_int := m[2]::int;
        if month_int is not null and day_int between 1 and 31 then
            return to_char(make_date(2000, month_int, day_int), 'FMMonth FMDD');
        end if;
    end if;

    return null;
end;
$$;


-- =============================================================================
-- 3. Multi-user birthday cleanup
-- =============================================================================

do $$
declare
    v_user_id uuid;
    v_canonical_id uuid;
    v_canonical_date date;
    v_canonical_month_day text;
begin
    for v_user_id in
        select distinct user_id
        from memories
        where structured_field = 'birthday'
           or lower(content) like '%birthday%'
           or lower(content) like '%ulang tahun%'
           or lower(content) like '%ultah%'
    loop
        v_canonical_id := null;
        v_canonical_date := null;
        v_canonical_month_day := null;

        with candidates as (
            select
                id,
                content,
                structured_field,
                structured_value,
                confidence,
                created_at,
                coalesce(superseded, false) as is_superseded,
                coalesce(
                    _phase415_parse_birthday_date(structured_value),
                    _phase415_parse_birthday_date(content)
                ) as parsed_date,
                coalesce(
                    _phase415_parse_birthday_month_day(structured_value),
                    _phase415_parse_birthday_month_day(content)
                ) as parsed_month_day
            from memories
            where user_id = v_user_id
              and (
                  structured_field = 'birthday'
                  or lower(content) like '%birthday%'
                  or lower(content) like '%ulang tahun%'
                  or lower(content) like '%ultah%'
              )
        )
        select id, parsed_date, parsed_month_day
        into v_canonical_id, v_canonical_date, v_canonical_month_day
        from candidates
        order by
            case
                when not is_superseded
                     and structured_field = 'birthday'
                     and structured_value ~ '^\d{4}-\d{2}-\d{2}$'
                     and parsed_date is not null then 1
                when not is_superseded
                     and structured_field = 'birthday'
                     and parsed_date is not null then 2
                when not is_superseded
                     and parsed_date is not null then 3
                when not is_superseded
                     and structured_field = 'birthday' then 4
                when not is_superseded then 5
                else 6
            end,
            coalesce(confidence, 0) desc,
            created_at desc
        limit 1;

        if v_canonical_id is not null then
            update memories
            set
                content = case
                    when v_canonical_date is not null
                        then 'User''s birthday is ' || to_char(v_canonical_date, 'FMMonth FMDD, YYYY')
                    when v_canonical_month_day is not null
                        then 'User''s birthday is ' || v_canonical_month_day
                    else content
                end,
                kind = 'fact',
                category = 'important_dates',
                structured_field = 'birthday',
                structured_value = case
                    when v_canonical_date is not null then v_canonical_date::text
                    when v_canonical_month_day is not null then v_canonical_month_day
                    else structured_value
                end,
                confidence = greatest(coalesce(confidence, 0), case when v_canonical_date is not null then 0.98 else 0.90 end),
                source_priority = coalesce(source_priority, 'explicit_user_statement'),
                superseded = false,
                superseded_by = null,
                superseded_at = null,
                last_confirmed_at = now()
            where id = v_canonical_id;

            -- Supersede duplicate birthday rows for the same user only.
            update memories
            set
                superseded = true,
                superseded_by = v_canonical_id,
                superseded_at = now()
            where user_id = v_user_id
              and id != v_canonical_id
              and coalesce(superseded, false) = false
              and (
                  structured_field = 'birthday'
                  or lower(content) like '%birthday%'
                  or lower(content) like '%ulang tahun%'
                  or lower(content) like '%ultah%'
              );

            -- Update identity profile only from this user's own canonical evidence.
            if v_canonical_date is not null then
                update user_identity
                set profile = jsonb_set(
                    coalesce(profile, '{}'::jsonb),
                    '{birthday}',
                    to_jsonb(v_canonical_date::text),
                    true
                ),
                updated_at = now()
                where user_id = v_user_id;
            elsif v_canonical_month_day is not null then
                update user_identity
                set profile = jsonb_set(
                    coalesce(profile, '{}'::jsonb),
                    '{birthday}',
                    to_jsonb(v_canonical_month_day),
                    true
                ),
                updated_at = now()
                where user_id = v_user_id
                  and not (coalesce(profile, '{}'::jsonb) ? 'birthday');
            end if;
        end if;
    end loop;
end $$;


-- =============================================================================
-- 4. Drop migration helper functions
-- =============================================================================

drop function if exists _phase415_parse_birthday_month_day(text);
drop function if exists _phase415_parse_birthday_date(text);
drop function if exists _phase415_month_num(text);
