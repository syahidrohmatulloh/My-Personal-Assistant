# Phase 4 — daily journal

Daily check-in with mood/energy/stress + reflection. Auto-extracts significant
life events from the reflection. Sidebar shows a subtle dot when you haven't
checked in today.

**No new SQL.** Phase 3 schema already covers everything we need.
**No new env vars.** No new services.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/phase4-files/. .
```

## Test locally

```
cd ~/my-assistant/backend
uv run uvicorn app.main:app --reload --port 8080

cd ~/my-assistant/frontend
npm run dev
```

In the browser:

1. Sidebar should show a new **Journal** link with an emerald dot
2. Click it. Pick mood/energy/stress on the -5 to +5 scale. Write a paragraph.
3. Save. Dot disappears.
4. Refresh — values persist (you can update later in the day).
5. Start a new chat → ask "how was my mood today?" — Claude should reference your numbers.

To test event extraction: in the journal note, write something significant
(e.g. *"Had the launch call with investors today, went better than expected"*).
Wait ~10 seconds after save. Go to `/memories` or check Supabase `life_events`
table — a row should appear.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Phase 4: daily journal + event extraction"
git push
```

## What this unlocks

- The assistant now has **continuous emotional data**, not just isolated mood mentions in chat
- Patterns become visible: stress over time, energy on certain days, mood trends
- Phase 5 (proactive briefings) becomes meaningful — the morning briefing can say *"yesterday you noted lower energy after the long meeting; today's calendar looks lighter"*

## Honest notes

- Event extraction is conservative on purpose. Most journal entries won't produce events; that's correct behavior.
- The mood scales are intentionally optional — you can journal with just text, or just numbers, or both.
- No streak counter, no gamification. By design — see the principles you locked in Phase 3.
