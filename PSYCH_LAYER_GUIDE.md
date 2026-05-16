# Psych layer (P0 + P1)

Two closely-related upgrades that close gaps identified vs ChatGPT's "psychological
companion" checklist:

**P0 — Adaptive emotional tone.** When recent self-reported state shows a clear
pattern (elevated stress, low mood, or high energy + positive mood), the prompt
builder injects a directive telling Claude how to modulate THIS conversation.
Quiet on neutral states — no noise injection.

**P1 — Self-reflection engine.** Reads journal entries + goal check-ins +
life events from past 1-2 weeks, asks Haiku to identify 1-3 patterns, writes
them to `self_reflections`. These already render in the prompt as PRIVATE
behavioral hints ("do NOT recite back to user") — so reflections influence
the agent's reasoning without becoming therapy talk.

## What's new

**Backend:**
- `app/services/prompt_builder.py` — adds `_emotional_directive()` function. Reads recent self-reported mood/energy/stress; if a clear pattern exists, returns a tone directive (otherwise None).
- `app/services/self_reflection.py` — `generate_weekly_reflection(user_id, lookback_days)`. Conservative — skips silently if <3 signals in window. Caps at 3 reflections per run.
- `app/routers/reflections.py` — `POST /reflections/generate` and `GET /reflections`. Manual trigger for now; cron in Phase 5.
- `app/main.py` — registers reflections router.

No SQL changes. `self_reflections` table already exists from Phase 3.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/psych-layer/. .
```

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "P0+P1: adaptive tone directive + self-reflection engine"
git push
```

## Test

### P0 — Adaptive tone

The directive is invisible to the user but visible in Claude's behavior. To
test, you need recent journal entries with extreme values.

Quick test:
1. Open `/journal`, log 2 entries within 3 days with **mood -3, energy -1,
   stress +3** and a short note like "really overwhelmed".
2. Open a chat, ask anything substantive (e.g. "what should I focus on this
   week?").
3. **Expected:** Claude's reply will be noticeably shorter, less option-laden,
   more validating. It won't *announce* "I see you're stressed" (anti-repetition
   doctrine still holds) — but the tone shifts.
4. To verify it's the directive firing (not random), check Fly logs — the
   prompt size sent to Claude should be larger than normal when directive
   is active.

To test the energetic variant: log 2 entries with **mood +3, energy +3,
stress 0** and note "feeling clear". Then ask "give me a list of things
I should tackle today." Reply should be sharper, less hedged.

### P1 — Self-reflection

Manual trigger:

```bash
curl -X POST https://my-assistant-backend.fly.dev/reflections/generate \
  -H "Authorization: Bearer $YOUR_JWT"
```

Or simpler: open browser DevTools on the app, paste in Console:
```js
fetch('/api/proxy/reflections/generate', { method: 'POST' }).then(r=>r.json()).then(console.log)
```

(If your app doesn't have a /api/proxy route, swap for the direct Fly URL with
an Authorization header pulled from your Supabase session.)

Expected response: `{count: 1-3, lookback_days: 14}`. If count is 0, you
don't have enough recent activity — that's correct behavior.

Inspect what was written:

```sql
select kind, content, created_at
from self_reflections
where user_id = auth.uid()
order by created_at desc
limit 10;
```

Should see 1-3 rows with specific content like:
- `pattern_noticed`: "User journals more consistently on weekends"
- `what_works`: "User responds well to direct answers without preamble"
- `open_question`: "When user mentions feeling 'flat', is venting or seeking advice?"

After reflections are written, they automatically appear in future chat
prompts under "## Private behavioral notes" — Claude reads them but never
quotes them back.

## How they interact

P0 modulates per-turn behavior (right now feels stressed → calm down).
P1 modulates over-time behavior (this user generally responds to X →
calibrate baseline).

Both feed the same prompt:
```
[Identity → Goals → People → Mood → Events → P1 reflections → P0 directive → Name]
```

The order matters. P0 is near the end so it has highest recency weight in
Claude's attention — overriding P1 for this turn when state demands it.

## Honest notes

- **P0 only fires on self-reported data.** Inferred mood is too low-confidence
  to drive tone changes. If the user never journals, P0 stays silent. That's
  correct — better silence than wrong inference.
- **P0 threshold tuning is conservative.** Stress avg ≥+2 OR mood avg ≤-2 OR
  (mood ≥+2 AND energy ≥+2). Edge cases (e.g. mood -2 AND energy -2 but no
  stress) won't trigger anything. Acceptable starting point. Tune later if
  patterns are too rare.
- **P1 doesn't run automatically yet.** No cron. Trigger manually for now,
  or hit it from a frontend button if you want. Cron via Fly scheduled
  machines comes in Phase 5 alongside Telegram briefings (they share infra).
- **P1 may write duplicate-ish reflections over time.** No dedup. The
  prompt builder limits to 5 most recent, so older ones age out. Run
  `decay_inferred_confidence()` periodically to drop confidence on stale ones.
- **No frontend UI** for either feature in this zip. P0 is invisible by design.
  P1 you can inspect via the GET endpoint or Supabase. A "Patterns I've noticed"
  page would be a nice addition later, but it's read-only and not blocking.

## What this does NOT do

Per ChatGPT's broader list (loneliness/dopamine safety layer, romantic
boundaries, FSM, voice psychology), these are skipped because:
- "Loneliness/dopamine layer" is marketing speak, not implementable.
- "Romantic boundaries" violates your CLAUDE.md doctrine — no romantic
  companion behavior in this product.
- "Voice psychology" is Phase 9 (post-voice). Not relevant pre-voice.
- "FSM" is over-engineering — you already have state via memory tables.
