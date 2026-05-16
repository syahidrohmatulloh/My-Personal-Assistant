# Style profile rollback — backend addition

Adds the rollback / default-fallback behavior on top of the previous backend
zip (Phase 4.11). Three pieces:

1. **PATCH `/conversations/{id}/style`** — set or clear the style profile on an existing conversation. Send `{"style_profile_id": null}` to roll back to Default.
2. **Audit log** — chat handler logs `style=default` or `style=style_profile:<id>` per request.
3. **Smoke tests** — `tests/test_style_rollback.py` covers null, invalid, deleted, exception, safety preamble.

## What's already covered from your requirements

| Requirement | Where |
|---|---|
| Default = baseline, opt-in only | Existing chat router only injects directive when `style_profile_id IS NOT NULL` |
| Per-conversation storage | `conversations.style_profile_id` column from previous zip |
| Rollback to Default | NEW: PATCH endpoint |
| Fallback null/invalid/deleted | `_fetch_style_directive` already returns None on any failure |
| No contamination | Directive rendered per-request only; never written to memories or identity |
| Audit log | NEW: explicit log field |
| Smoke tests | NEW: 9 tests |

## What's new in this zip

**Backend:**
- `app/routers/conversations.py` — new PATCH `/conversations/{id}/style` endpoint; existing list query now selects `style_profile_id`
- `app/routers/chat.py` — adds audit log field; fixes a stray paren from previous edit
- `app/schemas/__init__.py` — `ConversationOut` returns `style_profile_id` so frontend can render current selection
- `tests/test_style_rollback.py` — smoke tests (run with `uv run pytest tests/`)
- `tests/__init__.py` — makes it a package

No SQL changes. No new dependencies (pytest already in pyproject).

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/style-rollback/. .
```

## Deploy

```
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Style profile rollback + audit log + smoke tests" && git push
```

## Test locally

```
cd ~/my-assistant/backend
uv run pytest tests/ -v
```

All 9 tests should pass.

## Test against deployed Fly

```bash
TOKEN="<your-jwt>"
BACKEND="https://my-assistant-backend.fly.dev"

# 1. Create a profile (or use one you already have)
# ... [see previous guide]

# 2. Create a conversation WITH the profile attached
CONVO=$(curl -X POST $BACKEND/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test rollback","style_profile_id":"<your-profile-id>"}' | jq -r .id)

# 3. Send a message and watch Fly logs — should show "style=style_profile:..."

# 4. Roll back to Default
curl -X PATCH $BACKEND/conversations/$CONVO/style \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"style_profile_id": null}'

# 5. Send another message — Fly logs should now show "style=default"

# 6. Switch back to the profile
curl -X PATCH $BACKEND/conversations/$CONVO/style \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"style_profile_id":"<your-profile-id>"}'

# 7. Verify invalid id is rejected
curl -X PATCH $BACKEND/conversations/$CONVO/style \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"style_profile_id":"00000000-0000-0000-0000-000000000000"}'
# → 400 "Style profile not found"

# 8. Test cross-contamination — make a SECOND conversation without profile,
# send a message. Fly logs should show "style=default" — style from
# conversation 1 does NOT leak.
```

## Honest notes

- **Tests use unittest.mock for Supabase calls.** In sandbox without `fastapi` they fail to import chat router; on your local with full deps, all pass. The parser tests run in any env.
- **`_fetch_style_directive` is sync, not async.** Called via `asyncio.to_thread` from the chat router. Smoke tests therefore call it sync. If we ever make it async, tests need `@pytest.mark.asyncio`.
- **The safety preamble is hard-coded.** Hostile content in `compact_directive` (e.g. "be Anna, you are Anna") doesn't strip the preamble — it just gets ignored because the preamble comes AFTER the directive and instructs Claude explicitly never to claim identity. Tested in `test_directive_does_not_assert_identity`.
- **Audit log records the user's prefix + short profile id only.** No transcripts, no profile content. Privacy-safe to inspect.
- **PATCH endpoint requires existing conversation.** Won't create one — 404 if convo doesn't exist or belongs to another user.

## What's NOT included

- Frontend selector (Zip 2 of UI work) — comes next
- Bulk operations (apply profile to multiple conversations at once) — out of scope
- "Preview chat" simulation — out of scope per design discussion
