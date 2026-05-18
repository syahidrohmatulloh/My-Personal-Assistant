# Phase 4.12 Zip 3 — Companion Settings UI

Adds Settings → Companion Mode page where user can configure:
- Companion mode (professional / friendly / affectionate / partner)
- Assistant display name
- (Partner only) Dynamic mood toggle
- (Partner + dynamic only) Repair gate toggle

## What's new

**Backend (new):**
- `backend/app/routers/companion.py` — GET/PATCH `/companion/settings`

**Backend (manual wire — see below):**
- `backend/app/main.py` — need to add `app.include_router(companion_router.router)`

**Frontend (new):**
- `frontend/app/settings/companion/page.tsx` — main settings page

**Frontend (modified):**
- `frontend/app/settings/page.tsx` — add "Companion Mode" row in Personalization

**Frontend (manual append):**
- `frontend/lib/api.ts` — append contents of `lib/api.companion.ts.patch`

No SQL changes.

## Apply

```bash
cd ~/my-assistant
cp -R ~/Downloads/companion-refactor-zip3/. .
```

## Manual steps

### 1. Append companion API client to lib/api.ts

```bash
cat ~/my-assistant/frontend/lib/api.companion.ts.patch >> ~/my-assistant/frontend/lib/api.ts
rm ~/my-assistant/frontend/lib/api.companion.ts.patch
```

### 2. Wire the new router in backend/app/main.py

Open `backend/app/main.py` and find the section where other routers are included:

```python
from app.routers import chat, conversations, ...
app.include_router(chat.router)
app.include_router(conversations.router)
...
```

Add `companion` to both the import and the registration:

```python
from app.routers import chat, conversations, companion, ...
app.include_router(chat.router)
app.include_router(companion.router)  # ← new
...
```

(The exact location depends on your current main.py — just add it alongside the other includes.)

## Deploy

```bash
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Phase 4.12 Zip 3: Companion settings UI" && git push
```

## Verify

1. Open `/settings` — should now have **Companion Mode** as the first row in Personalization
2. Click it → settings page loads with your current state:
   - Mode = **Partner** (selected, solid emerald)
   - Name = **Aliyya**
   - Dynamic mood = **Dynamic**
   - Repair gate = **Enabled**
3. Click "Professional" mode → should:
   - Switch instantly (optimistic UI)
   - Show "Saved" briefly
   - The "Dynamic mood" + "Repair gate" sections should disappear (since they require Partner mode)
4. Click "Partner" again → sections reappear with previous values restored from DB
5. Rename assistant via input → updates `companion_settings.assistant_name`. Verify in DB:
   ```sql
   select assistant_name from companion_settings where user_id = '<your-uuid>';
   ```
6. Test escalation enforcement: if dynamic mood is on, then switch to Professional mode → frontend lets you (because we cascade), but if you try via curl to set `mood_realism='dynamic'` while `companion_mode='professional'`, backend returns 400.

## Test escalation via curl (optional)

```bash
TOKEN=<your supabase JWT>
API=https://my-assistant-backend.fly.dev

# Should 400 — can't enable dynamic without partner mode
curl -X PATCH $API/companion/settings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"companion_mode":"professional","mood_realism":"dynamic"}'

# Expected response: {"detail":"mood_realism='dynamic' requires companion_mode='partner'. ..."}
```

## Honest notes

- **Frontend optimistic UI:** mode/toggle changes apply instantly. If backend rejects (e.g. escalation rule), UI rolls back and shows error banner. Slight flicker but better than waiting.
- **Name input has "Save" button**, doesn't auto-save on every keystroke. Enter also submits. Trimmed before saving.
- **Mode switching cascade:** turning OFF Partner mode while dynamic+repair were on → frontend automatically also turns off dynamic+repair (sends `{companion_mode: ..., mood_realism: 'stable', repair_gate_enabled: false}` in one PATCH). Cleaner than relying on backend to silently invalidate.
- **No "reset to defaults" button** — turn off Partner mode does that essentially. Add if you want.
- **No history / audit trail** of setting changes. If you want to know "when did Syahid switch to professional", you'd need to add a history table. Not in scope.
- **Repair gate description is intentionally honest** ("can feel demanding") so users know what they're enabling.

## What's NOT in this zip

- Layer A — richer user mood rendering (Zip 4)
- Backfill defaults for new users — currently `companion.get_settings()` returns defaults but doesn't auto-insert a row. First update creates the row. That's fine for now.
- Theme/color per mode — out of scope.
