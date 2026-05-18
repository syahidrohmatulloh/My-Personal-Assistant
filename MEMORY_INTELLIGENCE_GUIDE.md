# Phase 4.14 — Memory Intelligence (Zip 5, revised v2)

Smarter memory extraction over a wider context window, with structured identity
writes, confidence + source-priority scoring, and conflict resolution via
supersede chain.

## What changed from v1 (review fixes)

- Schema now persists `structured_field` + `structured_value` columns
- `_find_superseded` for structured facts uses **deterministic eq lookup**, not ILIKE
- Service insert payload now includes structured field + value
- New test: `test_structured_supersede_uses_field_equality` proves deterministic supersede works
- New partial index for fast structured supersede lookups
- Guide verify queries updated accordingly

## What's new

**SQL (run in Supabase SQL Editor):**
- `schema_phase414_memory_intelligence.sql` — adds columns to `memories`:
  - `confidence` real (0..1)
  - `source_priority` text enum
  - `evidence` jsonb (verbatim quote snippets)
  - `category` text enum (identity / preferences / relationships / routines / goals / important_dates / constraints / other)
  - `structured_field` text (e.g. 'birthday', 'timezone' — enables deterministic supersede)
  - `structured_value` text (the actual value, e.g. '7 Januari')
  - `superseded` boolean + `superseded_by` uuid + `superseded_at` timestamp
  - `last_confirmed_at` timestamp
  - Two indexes: active memories, and active+structured_field for fast identity lookups
  - **Backwards compatible**: existing rows + existing code unaffected (all columns nullable / have defaults).

**Backend (new):**
- `backend/app/services/memory_intelligence.py` — extraction service
- `backend/tests/test_memory_intelligence.py` — 10 tests (4 required cases + 6 bonus)
- `backend/apply_memory_intel.py` — idempotent chat.py patcher

**Backend (patched via apply_memory_intel.py):**
- `backend/app/routers/chat.py` — 2 surgical patches:
  1. Import `memory_intelligence`
  2. Schedule extraction as a background task in parallel with existing `memory.extract_and_save`

No frontend changes. No touching `companion_settings`, `companion_mood_state`, or any other table beyond `memories` (additive only).

## Architecture

| | Existing `memory.py` | New `memory_intelligence.py` |
|---|---|---|
| Context window | Last user+assistant pair (2 messages) | Last 8 messages |
| Output | Generic facts/preferences | Categorized + source-priority-scored |
| Confidence | Not tracked | Tracked + threshold-gated by source |
| Identity writes | No | Yes — birthday/timezone/nickname/etc go to `user_identity.profile` |
| Conflict handling | Cosine dedupe only | Supersede chain on contradiction |
| Background task | Yes | Yes (runs in parallel) |

Both run after every chat turn. They do not compete — they write to the same table with different metadata.

## How extraction decides

1. Build window from last 8 messages.
2. Single Haiku call extracts candidates with:
   - content (third-person about user)
   - category (8-value enum)
   - source_priority (explicit_user_statement > user_answer_in_context > user_correction > repeated_pattern > assistant_confirmation)
   - confidence (0-1)
   - evidence (1-3 verbatim quotes)
   - structured_field + structured_value (for identity facts)
   - is_correction flag

3. Save thresholds per source:
   - `explicit_user_statement`: ≥ 0.80
   - `user_answer_in_context`: ≥ 0.75
   - `user_correction`: ≥ 0.70 (also marks old memory superseded)
   - `repeated_pattern`: ≥ 0.80
   - `assistant_confirmation`: ≥ 0.95 (effectively never; downgraded by hard guard)

4. Guards:
   - `assistant_confirmation` alone → ALWAYS skipped (per spec point 8).
   - `structured_field='birthday'` requires source ∈ {explicit / answer_in_context / correction}. Otherwise discarded — prevents random dates being saved as birthday.

5. Conflict resolution:
   - Structured identity → **deterministic lookup**: `eq("structured_field", "birthday")` finds old row regardless of category, no ILIKE guesswork.
   - Generic → cosine similarity ≥0.88 within same category → if `is_correction`, supersede; otherwise bump `last_confirmed_at` and skip insert.

6. For structured fields (birthday/timezone/nickname/assistant_name/name/location): also merge into `user_identity.profile` (field-level merge — does NOT replace whole profile). The new memory row carries `structured_field` + `structured_value` columns matching what was written to profile, so the two sources of truth stay aligned.

## Apply

```bash
cd ~/my-assistant
cp -R ~/Downloads/companion-refactor-zip5/. .

# 1. SQL
# Open Supabase SQL Editor, paste & run:
#   backend/schema_phase414_memory_intelligence.sql
# (Pilih "Run without RLS" — sama dengan tabel lain)

# 2. Patch chat.py
cd backend
python3 apply_memory_intel.py
```

Expected patcher output:
```
Patched app/routers/chat.py:
  + import memory_intelligence
  + schedule memory_intelligence extraction
```

## Test (no DB needed)

```bash
cd ~/my-assistant/backend
uv run python tests/test_memory_intelligence.py
```

Expected: `10 passed, 0 failed`.

## Verify SQL applied

In Supabase SQL Editor:
```sql
select column_name from information_schema.columns
where table_name = 'memories' and column_name in (
    'confidence', 'source_priority', 'evidence', 'category',
    'structured_field', 'structured_value',
    'superseded', 'superseded_by', 'superseded_at', 'last_confirmed_at'
)
order by column_name;
```
Should show all 10 columns.

## Deploy

```bash
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Phase 4.14: memory intelligence pipeline" && git push
```

## Verify in production

1. **Startup clean:**
   ```bash
   flyctl logs -a my-assistant-backend | tail -30
   ```
   `Application startup complete` + no ImportError.

2. **Birthday Q&A test** (the canonical case):
   Open chat → Aliyya. Send:
   ```
   kamu tau ga ulang tahunku kapan?
   ```
   Wait for her reply. Then:
   ```
   7 Januari hehe
   ```
   Wait for her acknowledgment. Within ~5 seconds (background task), check:
   ```sql
   select content, category, source_priority, confidence,
          structured_field, structured_value
   from memories
   where user_id = '<your-uuid>'
   order by created_at desc
   limit 5;
   ```
   Should see a row with:
   - content like "User's birthday is January 7"
   - `category='important_dates'`
   - `source_priority='user_answer_in_context'`
   - `confidence ~ 0.85`
   - `structured_field='birthday'`
   - `structured_value='7 Januari'`

   And:
   ```sql
   select profile -> 'birthday' from user_identity where user_id = '<your-uuid>';
   ```
   Should return `"7 Januari"` (or similar).

3. **Log audit:**
   ```bash
   flyctl logs -a my-assistant-backend | grep memory_intelligence
   ```
   Should see lines like:
   ```
   memory_intelligence: saved 'User's birthday is January 7' (category=important_dates, source=user_answer_in_context, conf=0.88)
   memory_intelligence: identity 7ac753fa set birthday='7 Januari' (prev=None)
   memory_intelligence: audit={'candidates': 1, 'saved': 1, 'skipped': 0, 'superseded': 0}
   ```

4. **Correction test:**
   Tell Aliyya later:
   ```
   sorry tadi salah, ulang tahunku 8 Januari deh bukan 7
   ```
   Check:
   ```sql
   select content, superseded, superseded_by, superseded_at
   from memories
   where user_id = '<your-uuid>'
   and category = 'important_dates'
   order by created_at desc;
   ```
   Old "January 7" row should have `superseded=true`. New "January 8" row should have `superseded=false`.

   And user_identity.profile.birthday should now be "8 Januari".

## Rollback

```bash
cd ~/my-assistant/backend
git checkout app/routers/chat.py
rm app/services/memory_intelligence.py
flyctl deploy
```

For SQL: columns added are additive — they can stay even after code rollback. They just won't be used. If you really want them gone:
```sql
alter table memories drop column if exists confidence;
alter table memories drop column if exists source_priority;
alter table memories drop column if exists evidence;
alter table memories drop column if exists category;
alter table memories drop column if exists superseded;
alter table memories drop column if exists superseded_by;
alter table memories drop column if exists superseded_at;
alter table memories drop column if exists last_confirmed_at;
```

## Honest notes

- **Two extraction passes per turn (`memory.py` + `memory_intelligence.py`)** — slight cost increase per chat turn. Each Haiku call is ~$0.001. Acceptable. Can collapse into one later if needed.
- **Background task latency:** new task adds 1-3s of background work per chat turn, but doesn't block reply.
- **Identity field merge isn't atomic** — `user_identity` read-then-write has a tiny race window. Acceptable since same-user writes are serialized in practice.
- **Conflict detection for structured fields uses ILIKE** — searches for the field name in memory content. Conservative — won't match all phrasings. Edge cases: if old memory says "Born January 7" without the word "birthday", supersede may miss it. Not a regression vs current behavior.
- **No vector index update on existing column adds** — pgvector index for cosine is on `embedding` which already existed. New columns don't need indexes for the read paths we care about (the existing `match_memories` RPC unchanged).
- **`match_memories` RPC doesn't filter `superseded`** unless you modify it. Active+superseded rows compete in retrieval — but supersede sets confidence/recency anyway. If you want strict filtering, update the RPC to add `where superseded = false`. Not in this zip.
- **No category-aware retrieval yet.** The new `category` column is written but `retrieve_relevant` still does plain cosine across all categories. Future zip could prioritize by category match.

## What's NOT in this zip

- Updating `match_memories` to filter superseded.
- Category-aware retrieval boost.
- Repeated pattern detection across turns / sessions (would need a separate aggregate job).
- A UI to view + edit extracted memories. Existing `/memories` page should still display them.
- Merging the two extraction services (`memory.py` + `memory_intelligence.py`) into one. Keep separate for now — easier to roll back, easier to A/B.
