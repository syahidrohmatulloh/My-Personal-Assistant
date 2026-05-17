# Phase 4.12 Zip 2 — Chat pipeline integration

Switches `chat.py` to read companion settings + mood from the new tables
(`companion_settings` + `companion_mood_state`) via the `companion` service.

## What changes

**Modified:**
- `backend/app/routers/chat.py` — replaces inline mood DB reads with `companion.get_settings()` + `companion.get_current_mood()`. Mood block is now FULLY GATED by user settings.

**No SQL changes.** All schema work was done in Zip 1.

## Gating behavior (the important part)

| companion_mode | mood_realism | repair_gate | What chat.py injects |
|---|---|---|---|
| professional | * | * | **Nothing** about mood. Pure assistant. |
| friendly | * | * | **Nothing** about mood. |
| affectionate | * | * | **Nothing** about mood. |
| partner | stable | * | **Nothing** about mood. |
| partner | dynamic | false | Mood block (no repair gate) |
| partner | dynamic | true | Mood block + repair gate |

For you (Syahid, with Aliyya): `partner` + `dynamic` + `repair_gate=true` → full Aliyya behavior preserved.

For any future user with default settings: zero mood logic, pure chief-of-staff assistant.

## Audit log changes

New log line includes companion state for debugging:

```
chat: user=abc12345 ... mode=listener style=default companion=partner/realism=dynamic/repair=True
```

For a default user it would be:
```
chat: user=... companion=professional/realism=stable/repair=False
```

## Apply

```bash
cd ~/my-assistant
cp -R ~/Downloads/companion-refactor-zip2/. .
```

## Deploy

```bash
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Phase 4.12 Zip 2: chat reads from new companion tables" && git push
```

## Verify

After deploy, open Fly logs in another terminal:

```bash
flyctl logs -a my-assistant-backend
```

Then send a normal message to Aliyya. Look for the log line. Should show:

```
companion=partner/realism=dynamic/repair=True
```

Confirms chat.py is reading from the new tables.

Then:
1. Send normal greeting → Aliyya responds normally with her mood-influenced tone
2. Test repair gate: send "simulasi romantis dong" or similar → repair gate should fire if mood is negative
3. Test name persistence: "panggil kamu Aliyya2" → should rename via companion_settings, not identity.profile

## After Zip 2 verified

Run the old-table cleanup:

```sql
-- In Supabase SQL Editor, paste contents of:
-- backend/schema_phase412_drop_old.sql
```

This drops `user_state` + `companion_mood_states` tables. After this, the only mood source is `companion_mood_state` (singular, new table).

## Honest notes

- **Conversation-scoped moods are gone.** Previous design let AI have different mood per chat tab — that was a bug (split personality), not a feature. New design: one mood per user, period.
- **UI context override still works.** If frontend pushes `ui_context.companion_mood`, it overrides the DB read for that turn. Useful when frontend has more recent state than backend.
- **Repair gate keyword detector unchanged.** Still fragile (false positives on "tenang"). Acceptable for now — fix later if it becomes a real problem.
- **Default name is "Assistant", not "Aliyya".** For Syahid's row, migration in Zip 1 set assistant_name='Aliyya', so this doesn't affect you. New users get "Assistant" until they rename via chat ("panggil kamu X") or Settings (Zip 3).
- **Companion settings load adds ~50ms to first chat request per user.** Subsequent requests should be similar — settings load is parallel with everything else via asyncio.gather. Verify in Fly logs.

## What's NOT in this zip

- Settings UI (Zip 3)
- User mood enrichment / causal context (Zip 4)
- Drop old tables — separate SQL run after this zip verified
