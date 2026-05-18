# Phase 4.15 — Deterministic Profile + Memory Hygiene (Zip 6 v2)

Fixes two bugs:
1. Age miscalculated by LLM (31 vs 30 confusion)
2. Birthday memories duplicated in DB

Plus tightens memory retrieval to respect `superseded`.

## What's new

**SQL (`schema_phase415_memory_hygiene.sql`):**
- Drops & recreates `match_memories` RPC — now filters `superseded=false`
- Casts `m.confidence::real as confidence` for RPC return compatibility
- Auto-cleanup birthday duplicates **per user**: picks one canonical birthday row per user, normalizes full dates to ISO `YYYY-MM-DD` when a year is clearly known, supersedes duplicates for that same user only
- Updates `user_identity.profile.birthday` per user from that user's own canonical birthday evidence
- Keeps memory `content` human-readable, e.g. `User's birthday is January 7, 1995`; ISO lives in `structured_value`

**Backend (new):**
- `app/services/deterministic_profile.py` — parses birthdays, computes age from browser local date, renders bilingual hint for the prompt
- `tests/test_deterministic_profile.py` — 29 tests covering parser edge cases, age math, and rendering

**Backend (patched via scripts):**
- `app/routers/chat.py` — `apply_phase415.py` injects profile runtime block
- `app/routers/memories.py` — `apply_memories_filter.py` adds `.eq("superseded", False)` to list endpoint

## What ChatGPT's review proposed vs what's in this zip

| ChatGPT's idea | This zip |
|---|---|
| Age calculator deterministic | ✅ Same approach, fixed `local_time_iso` key |
| Drop & recreate match_memories RPC | ✅ Same |
| Auto-cleanup birthday duplicates | ✅ Same logic, idempotent via DO block |
| Python double-filter in `memory.py` | ❌ Skipped — RPC filter is sufficient, double-filter is redundant + fragile to whitespace |
| Frontend `lib/api.ts` patch | ❌ Skipped — your api.ts doesn't use Supabase client directly. Fixed at backend router level instead. |
| Inline `python3 <<'PY'` script in chat.py | ❌ Replaced with anchored patcher (same pattern as Zip 4 + Zip 5) — bails on conflict, idempotent |

## How the deterministic profile works

For each chat turn:
1. `life_model.get_identity` returns `user_identity` row (already happens via `get_context`)
2. `render_profile_runtime_context(identity, ui_context)` builds the prompt block
3. Block tells Claude:
   - Canonical ISO birthday (`1995-01-07`)
   - Human-readable Indonesian: `"7 Januari 1995"` ← use this if replying in ID
   - Human-readable English: `"January 7, 1995"` ← use this if replying in EN
   - Computed age (`31`) with the local date used (`2026-05-18`)
   - Hard rule: do NOT recalculate age

When kamu tanya "berapa umurku?", Claude reads the precomputed `31` and doesn't have to do math. When kamu tanya in English "when's my birthday?", Claude picks the English-formatted string.

## Apply

```bash
cd ~/my-assistant
cp -R ~/Downloads/memory-intelligence-zip6/. .
```

### 1. SQL

Open Supabase SQL Editor, paste & **Run without RLS**:
- `backend/schema_phase415_memory_hygiene.sql`

### 2. Patch chat.py

```bash
cd ~/my-assistant/backend
python3 apply_phase415.py
```

Expected:
```
Patched app/routers/chat.py:
  + import render_profile_runtime_context
  + inject profile runtime block
```

### 3. Patch memories.py router

```bash
python3 apply_memories_filter.py
```

Expected (one of):
- `Patched app/routers/memories.py (matched pattern ...)` — success
- `Filter already present in memories.py. No changes made.` — idempotent skip
- `ERROR: could not find a recognizable list query` — your memories.py uses a different pattern; do manual patch (instructions in error output)

### 4. Tests

```bash
uv run python tests/test_deterministic_profile.py
```

Expected: `29 passed, 0 failed`.

## Verify SQL applied

```sql
-- A. All birthday-related memories across users
select user_id, id, content, structured_field, structured_value, confidence,
       superseded, superseded_by, created_at
from memories
where lower(content) like '%birthday%'
   or lower(content) like '%ulang tahun%'
   or lower(content) like '%ultah%'
   or structured_field = 'birthday'
order by user_id, superseded, created_at desc;

-- B. No user should have more than one active structured birthday memory
select user_id, count(*) as active_birthday_count
from memories
where structured_field = 'birthday'
  and coalesce(superseded, false) = false
group by user_id
having count(*) > 1;
-- Expected: zero rows

-- C. Check Syahid specifically
select content, superseded, structured_field, structured_value
from memories
where user_id = '7ac753fa-4ca9-40c7-82bc-dd5566f6bd5c'
  and (lower(content) like '%birthday%' or structured_field = 'birthday')
order by created_at desc;
-- Expected: one active canonical birthday row with structured_value='1995-01-07'; duplicates superseded=true

-- D. Canonical birthday in identity for Syahid
select profile -> 'birthday' as birthday
from user_identity
where user_id = '7ac753fa-4ca9-40c7-82bc-dd5566f6bd5c';
-- Expected: "1995-01-07"

-- E. RPC filters superseded and casts confidence consistently
select pg_get_functiondef('match_memories(uuid, vector(1024), integer)'::regprocedure);
-- Expected: function body contains `coalesce(m.superseded, false) = false`
-- and `m.confidence::real as confidence`
```

## Deploy

```bash
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Phase 4.15: deterministic profile + memory hygiene" && git push
```

## Test in production

### A. Age computed correctly
Send Aliyya (in Indonesian):
```
berarti sekarang umurku berapa?
```
Expected reply: mentions **31** (not 30, not 30-something).

Then in English:
```
when's my birthday again?
```
Expected: "January 7, 1995" (English formatting), and if she mentions age, "31".

### B. Memories page clean
Open `/memories` page. Birthday should show **once**, with human-readable canonical content like "User's birthday is January 7, 1995". The ISO value should live in `structured_value`, not in the visible content. The 3+ old duplicates should be hidden.

### C. Audit log
```bash
flyctl logs -a my-assistant-backend | grep -E "(memory_intelligence|profile)"
```
Look for prompt context being assembled correctly.

## Rollback

```bash
cd ~/my-assistant/backend
git checkout app/routers/chat.py app/routers/memories.py
rm app/services/deterministic_profile.py
flyctl deploy
```

For SQL: the new `match_memories` is a strict improvement (filters are additive). The auto-cleanup is irreversible without a backup — but rows are just marked `superseded=true`, not deleted. To revert:
```sql
update memories
set superseded = false, superseded_by = null, superseded_at = null
where user_id = '7ac753fa-4ca9-40c7-82bc-dd5566f6bd5c'
  and superseded_at > now() - interval '1 hour';
```

## Honest notes

- **The cleanup SQL is multi-user**. It loops per `user_id`, never cross-links users, and supersedes birthday duplicates only within the same user.
- **Cleanup is idempotent**. Re-running should not create rows. If a user later adds a newer birthday correction, the canonical selection may choose the highest-confidence/newest active birthday evidence for that same user; this is intended but should still be monitored like any data migration.
- **Age in the prompt is the user's age TODAY, not as-of any specific past message.** If you ask "how old was I in 2020?", Claude will still have to compute — which is fine for past dates, just not for "right now".
- **Bilingual rendering is a hint, not a hard rule.** Claude usually follows ("when in Indonesian say X"), but if you're in a mixed-language conversation it picks the dominant language. That's acceptable behavior.
- **Memory retrieval RPC now drops `superseded=true` rows entirely** — they won't appear in any cosine-search context. They still exist in the DB (for audit) and the supersede chain is queryable directly.
- **Backward compat for legacy profile values**: if `profile.birthday` is still "7 Januari 1995" instead of ISO, the parser handles it. So even if you skip the SQL update, the runtime works.

## What's NOT in this zip

- A UI to manually edit / archive memories from the Memories page.
- Timezone-based daily age refresh (right now age is computed per-request from `ui_context.local_time_iso`).
- Per-user cleanup tooling — adding new users with messy birthday data would need running the SQL with their UUID.


## Zip 6 v2 SQL changes vs original Zip 6

- Removed hard-coded Syahid UUID from the cleanup block.
- Birthday cleanup now applies per user.
- Full birthday dates are normalized to ISO `YYYY-MM-DD` only when a year is clearly present.
- Month/day-only birthdays are not given a fake year.
- Canonical memory content remains human-readable.
- `match_memories` uses `m.confidence::real as confidence` to avoid numeric/real return-type mismatch.
