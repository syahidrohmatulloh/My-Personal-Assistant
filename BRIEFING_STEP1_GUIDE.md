# Morning briefings (Step 1)

Personal briefing generated the first time the user opens the app each day.
Tap to start a conversation seeded with the briefing.

Backend generates synchronously the first time the day's briefing is requested
(adds ~1.5s to the first chat page load). Subsequent opens that day return
the cached briefing immediately.

## What's new

**Backend:**
- `schema_phase47_briefings.sql` — `daily_briefings` table
- `app/services/briefing.py` — generation via Haiku using `get_user_context`
- `app/routers/briefing.py` — GET `/briefing/today?date=YYYY-MM-DD`, POST `/briefing/{id}/open`
- `app/main.py` — router registered

**Frontend:**
- `app/chat/page.tsx` — briefing card on the empty chat home
- `lib/api.ts` — `getTodayBriefing()`, `openBriefing()`

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/briefing-step1/. .
```

## SQL — run once in Supabase SQL Editor

Paste contents of `backend/schema_phase47_briefings.sql`.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Phase 4.7 Step 1: morning briefing card"
git push
```

## Test

1. Open `/chat` (root, no conversation selected). Should see briefing card after ~1.5s.
2. Card content should reference YOUR specific goals/people/mood patterns — not generic.
3. Reload — briefing loads instantly (cached on server).
4. Tap card → creates new conversation seeded with briefing, navigates to it.
5. Open `/chat` next day → fresh briefing generated (because `briefing_date` differs).

## What this is NOT

- **Not scheduled.** Generation only happens on first open of the day. If user
  doesn't open the app, no briefing exists. Step 2 (cron-based generation)
  comes next.
- **Not notification.** No push, no email, no Telegram. Just on-screen card.
- **Not interactive.** The briefing is text. User can tap to start a chat
  about it, but the briefing itself doesn't have buttons or actions.

## Honest notes

- **First-open latency:** ~1.5s for Haiku call. Could be moved to background
  if it's annoying — but then user might see "no briefing today" and miss it.
  Sync feels more reliable for now.

- **No briefing for brand-new users:** if `render_context` returns empty
  (no identity, no goals, no nothing), generation returns null. User sees
  the regular empty state. By design — a briefing about an empty life model
  would feel hollow.

- **Briefing card replaces empty state ONLY on `/chat` root.** If user opens
  the app directly into an existing conversation URL (`/chat/<id>`), they
  don't see the briefing. That's intentional — briefing belongs on the
  home/empty screen, not interrupting an existing chat.

- **Briefing uses user's BROWSER timezone for the date check.** Frontend
  computes `YYYY-MM-DD` from `new Date()` and sends to backend. Robust
  across most cases; edge case is users who travel timezones mid-day
  (briefing would re-generate). Acceptable.

- **Quality depends on context.** If user only has identity + 1 goal + no
  people + no journal, briefing will be short. If they have rich context,
  briefing surfaces specific things. Quality grows with usage.
