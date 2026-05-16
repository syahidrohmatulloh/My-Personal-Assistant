# Style Profiles — Backend (Zip 1 of 2)

Backend foundation for "Conversation Style Profiles". Zip 2 (UI) follows
after this is confirmed working.

## What's new

**SQL:**
- `schema_phase411_style_profiles.sql` — `style_profiles` table + `conversations.style_profile_id` FK

**Backend:**
- `app/services/style_parser.py` — WhatsApp / Telegram / plain text detection & parsing
- `app/services/style_extractor.py` — Haiku-based structured profile extractor (Pydantic-validated)
- `app/routers/style_profiles.py` — analyze, list, create, rename, delete
- `app/routers/chat.py` — fetches style profile when conversation has one, injects compact directive + safety preamble into prompt
- `app/routers/conversations.py` — `style_profile_id` accepted at conversation creation
- `app/schemas/__init__.py` — `CreateConversationIn` gains `style_profile_id`
- `app/main.py` — registers style_profiles router

## Privacy contract

**The transcript is NEVER stored.** Analyze endpoint processes it in memory and discards. Only the extracted style JSON survives in `style_profiles.extracted_style`.

If the user wants to re-analyze, they paste again. That's by design.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/style-profiles-backend/. .
```

## SQL — run once in Supabase SQL Editor

Paste contents of `backend/schema_phase411_style_profiles.sql`. Idempotent.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Phase 4.11: style profiles backend"
git push
```

## Test (curl)

Get your JWT from browser DevTools (Supabase session):
```js
const { data: { session } } = await window.supabase.auth.getSession()
console.log(session.access_token)
```

Then:

```bash
TOKEN="<your-jwt>"
BACKEND="https://my-assistant-backend.fly.dev"

# 1. Analyze a paste
curl -X POST $BACKEND/style-profiles/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @- <<'EOF'
{
  "transcript": "[9/5/24, 10:23 PM] Anna: hey beb udah makan blm? \n[9/5/24, 10:24 PM] Anna: aku tadi beli sushi 🍣 lumayan lah \n[9/5/24, 10:24 PM] Anna: btw kamu jadi meeting yg jam 8? jangan lupa istirahat ya \n[9/5/24, 10:25 PM] Anna: sayang  \n[9/5/24, 10:30 PM] Anna: ok ttyl 👋"
}
EOF
```

Should return:
```json
{
  "profile": { "display_name": "Anna", "dominant_language": "Indonesian", ... },
  "sample_count": 5,
  "source_type": "whatsapp",
  "suggested_name": "Anna"
}
```

# 2. Save it:
```bash
curl -X POST $BACKEND/style-profiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "profile_name": "Anna casual",
    "source_type": "whatsapp",
    "extracted_style": { ... PASTE the profile from step 1 ... },
    "sample_count": 5
  }'
```

# 3. List:
```bash
curl $BACKEND/style-profiles -H "Authorization: Bearer $TOKEN"
```

# 4. Create a conversation using it:
```bash
curl -X POST $BACKEND/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test style", "style_profile_id":"<profile-id-from-step-2>"}'
```

# 5. Send a message in that conversation and observe Claude's tone shift. Check Fly logs for the chat handler invocation — the prompt should include "## Communication style for this conversation".

## Honest notes

- **The Haiku extractor will sometimes hallucinate** common_phrases that don't appear in the transcript. Acceptable — we explicitly tell it to use empty list if uncertain, but it doesn't always listen. Low-impact: the compact_directive is what actually shapes Claude's reply.
- **The parser is conservative.** If your transcript is unusual (custom format, lots of system messages, mixed languages with odd punctuation), it falls back to plain text. Style extraction still works, just with lower confidence.
- **Style + companion mode + adaptive tone can clash.** When all three fire, the prompt gets long. Mode and emotional directive take priority because they're per-turn — style is per-conversation. If you notice tone confusion, that's the cause and we can re-order priority.
- **No frontend yet.** Zip 2 adds Settings page + style selector dropdown. Until then, you can only test via curl.

## What's NOT in this zip

- UI (Settings page, style selector, preview, rename, delete) — Zip 2
- "Practice mode" preview chat with profile — out of scope per design discussion
- JSON editing of extracted profile — out of scope (use rename + re-analyze instead)
- File upload (drag-drop) — paste textarea only in Zip 2; can add later
