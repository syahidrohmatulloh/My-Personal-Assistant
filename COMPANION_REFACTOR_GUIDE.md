# Phase 4.12 — Companion Settings + Mood Refactor (Zip 1 of 4)

Schema + service refactor. **Chat behavior unchanged in this zip.**

## What's new

**SQL (run in Supabase SQL Editor, in order):**
1. `schema_phase412_companion.sql` — creates `companion_settings` + `companion_mood_state` tables
2. `schema_phase412_migrate.sql` — copies data from `user_state` + `companion_mood_states` (global scope only); auto-escalates your user (Syahid) to partner mode with Aliyya

**Backend (new):**
- `app/services/companion.py` — clean API for settings + mood, with escalation rules enforced

**Backend (manual delete after applying zip):**
- `app/services/user_state.py` — orphan code, never wired to chat.py. Delete it.

**DO NOT run yet:**
- `schema_phase412_drop_old.sql` — drops old tables. Wait until Zip 2 verified.

## Why this design

ChatGPT's previous design had two issues:
1. **`user_state` was dead code** — service created but never imported by `chat.py`. So `mode`, `romantic_baseline`, `nickname` fields never affected prompt. All settings UI in ChatGPT's design was theater.
2. **`companion_mood_states` was conversation-scoped** — AI could have different moods in different chat tabs. That's split-personality, not human-like. Real humans have one mood across contexts.

New design fixes both:
- Single source of truth per user (`companion_settings` + one row per user in `companion_mood_state`)
- Schema-level commit to repo (was only in Supabase before)
- Opt-in escalation ladder: professional → friendly → affectionate → partner. Mood only kicks in at 'partner'. Repair gate only kicks in if user explicitly enables `mood_realism='dynamic'` + `repair_gate_enabled=true`.

## Your migration (Syahid)

The migration script auto-escalates you because you have an existing mood state row. After running it:
- `companion_settings.companion_mode` = 'partner'
- `companion_settings.assistant_name` = 'Aliyya'
- `companion_settings.mood_realism` = 'dynamic'
- `companion_settings.repair_gate_enabled` = true
- `companion_mood_state.mood` = whatever your latest global-scope mood was (likely 'romantic')

Your Aliyya behavior is preserved.

## Apply

```bash
cd ~/my-assistant
cp -R ~/Downloads/companion-refactor-zip1/. .

# 1. Delete orphan service
rm backend/app/services/user_state.py

# 2. Run SQL in Supabase SQL Editor, IN ORDER:
#    - schema_phase412_companion.sql
#    - schema_phase412_migrate.sql
#    (do NOT run schema_phase412_drop_old.sql yet — wait for Zip 2)
```

## Verify

In Supabase SQL Editor:

```sql
-- Should show 1 row, your user, mode='partner', name='Aliyya'
select user_id, companion_mode, assistant_name, mood_realism, repair_gate_enabled
from companion_settings;

-- Should show 1 row, your latest mood
select user_id, mood, intensity, valence, expires_at
from companion_mood_state;
```

## Deploy

```bash
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Phase 4.12 Zip 1: companion settings schema + service" && git push
```

## What's NOT in this zip

- Chat integration (Zip 2)
- Settings UI (Zip 3)
- Layer A — richer user mood rendering (Zip 4)

Chat behavior is **unchanged**. The new tables exist but `chat.py` doesn't read from them yet. Your Aliyya keeps working via the old `companion_mood_states` table (still queried by `_fetch_companion_mood_for_prompt`). Zip 2 will switch chat.py to read from new tables, then Zip 1's old tables become safe to drop.

## Honest notes

- **`user_state.py` deletion is manual** because I can't delete files via zip. Run `rm backend/app/services/user_state.py` after applying. If you forget, nothing breaks — but it's confusing dead code.
- **Migration is idempotent.** You can re-run `schema_phase412_migrate.sql` safely; `on conflict do nothing` prevents duplicate rows.
- **TTL is 30 minutes** matching your previous mood_states. Wired in via Python (`now() + timedelta(minutes=30)`) not SQL expression because supabase-py mangles raw SQL in upserts.
- **RLS is disabled** on both new tables, matching your existing service-role pattern.
- **No tests** because tests against external Supabase = flaky. Service layer is small enough to verify by reading.
