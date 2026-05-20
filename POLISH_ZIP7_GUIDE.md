# Phase 4.16 polish (Zip 7) — Quick wins + UI cleanup

Five small fixes from the audit. Low risk, low effort, high signal.

## What's included

| # | Fix | File |
|---|---|---|
| 1 | Structured logging in auth (replaces `print()` + sanitizes 401 detail) | `backend/app/core/auth.py` (replace) |
| 2 | Streaming error logs full trace, returns generic client message | `backend/app/routers/chat.py` (via patcher) |
| 3 | Schema dump script for disaster recovery | `scripts/dump_schema.sh` (new) |
| 4 | Updated README reflecting Phase 4.15+ state | `README.md` (replace) |
| 5 | Memory page: drop redundant `kind` Badge (saved as 2 pills → 3 pills, was 4) | `frontend/app/memories/page.tsx` (via patcher) |

No SQL changes. No `companion_*` table touched. No new services. Pure polish.

## Apply

```bash
cd ~/my-assistant
cp -R ~/Downloads/polish-zip7/. .

# 1 — auth.py is a direct replacement (file already verified line-for-line)
# (done by cp -R above)

# 2 — patch chat.py streaming error
cd backend
python3 apply_streaming_log.py
cd ..

# 3 — make schema dump script executable
chmod +x scripts/dump_schema.sh

# 4 — README updated by cp -R

# 5 — patch memories page
python3 frontend/apply_memories_polish.py
```

Expected:
- `Patched app/routers/chat.py: streaming error now logs full trace, sends generic message.`
- `Patched frontend/app/memories/page.tsx: removed redundant kind Badge from memory pills.`

## Optional — generate schema snapshot once

```bash
# Get connection string from Supabase Dashboard
# → Project Settings → Database → Connection string → URI

SUPABASE_DB_URL="postgresql://postgres:[PASSWORD]@db.[ID].supabase.co:5432/postgres" \
  ./scripts/dump_schema.sh
```

Output: `backend/schema_snapshot.sql` — commit ke git. Regenerate occasionally (after major schema changes), tidak per deploy.

## Test

```bash
cd backend
uv run python -m py_compile app/core/auth.py app/routers/chat.py
```

Should print nothing (success).

## Deploy

```bash
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Phase 4.16 polish: logging + memory pill cleanup + README" && git push
```

## Verify after deploy

**1. Auth logging:**
```bash
flyctl logs -a my-assistant-backend | grep "JWT verification"
```
Kalau ada token invalid, lihat line `JWT verification failed: ...` (warn level). Sebelumnya: `🔴 JWT VERIFICATION FAILED:` via print.

**2. Streaming error logging:**
Tidak ada cara mudah untuk trigger — kecuali ada bug, ga akan keluar. Tapi kalau bug terjadi, sekarang log.exception() akan dump full traceback ke Fly logs.

**3. Memory page UI:**
Open `/memories`. Tiap memory pill harusnya 3 pills max (category + conf + source), bukan 4. Pill "fact" / "preference" yang redundant hilang.

## Notes about other `except Exception` in chat.py

Grep showed 3 bare `except Exception` blocks at lines 996, 1136, 1263. Patch ini fix yang **paling exposed** (line 996 — streaming error sent to user).

Lines 1136 + 1263 — saya tidak modify. Kemungkinan besar mereka catch operational errors (memory save, title gen) yang sudah punya log.warning(). Kalau kamu ingin upgrade those too, kasih tahu — saya bisa kasih patcher tambahan.

## Rollback

```bash
cd ~/my-assistant
git checkout backend/app/core/auth.py backend/app/routers/chat.py \
              frontend/app/memories/page.tsx README.md
rm scripts/dump_schema.sh backend/schema_snapshot.sql 2>/dev/null
flyctl deploy -c backend/fly.toml
```

## What's NOT in this zip (deliberate)

- chat.py extraction into helpers — that's Phase 4.16 architectural work, not polish
- Settings page rebalance — bigger UI change, separate iteration
- Removing `ANTHROPIC_MODEL` env validation — Kimi was wrong, model name `claude-sonnet-4-6` is current
- Rate limiting — premature for personal use
- Three.js removal — would need broader audit of `ambient-background.tsx` first
