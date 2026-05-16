# Phase 4.10 — Context depth + companion mode

Three targeted gaps closed:

1. **Goal check-ins render in prompt.** Each active goal now shows its latest momentum + check-in note inline. Assistant knows where you're at on each goal, not just that goals exist.

2. **Relationship notes render in prompt.** Each important person now shows up to 3 most recent notes (recent_event, sentiment, follow_up, fact). Assistant has context about Anna's bad week, not just that Anna exists.

3. **Companion mode detection per turn.** A small Haiku classifier runs in parallel with other context-fetching work. Classifies user message into: strategist / listener / motivator / challenger / reflective / practical. The detected mode injects a 30-token directive into the prompt shaping reply style.

## What's new

**SQL:**
- `schema_phase410_context_notes.sql` — extends `get_user_context()` to fetch latest check-in per goal and top 3 notes per person. **Idempotent (CREATE OR REPLACE)**.

**Backend:**
- `app/services/prompt_builder.py` — extends goals + people rendering to surface check-ins and notes
- `app/services/companion_mode.py` — new service. `detect_mode()` classifier + `directive_for()`. Short-circuits for trivial messages and obvious "practical" queries to skip Haiku call.
- `app/routers/chat.py` — adds mode detection to the parallel asyncio.gather, injects directive into volatile_context

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/phase410/. .
```

## SQL — run once in Supabase SQL Editor

Paste contents of `backend/schema_phase410_context_notes.sql`. Idempotent.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Phase 4.10: render check-ins + notes, companion mode detection"
git push
```

## Test

### Test 1: Goal check-ins render

1. Open `/goals`, ensure you have at least one active goal
2. Open the goal in Supabase Table Editor → goal_check_ins → insert a row manually:
   ```sql
   insert into goal_check_ins (user_id, goal_id, momentum, note)
   values (auth.uid(), '<your-goal-id>', 3, 'Made real progress this week');
   ```
3. Open a new chat, ask "how am I doing on my goals?"
4. Assistant should reference the specific momentum + note — not just say "you have goals"

### Test 2: Relationship notes render

1. Open `/people`, add a person (e.g. Anna, wife, importance 10)
2. In Supabase Table Editor → relationship_notes → insert a row:
   ```sql
   insert into relationship_notes (user_id, person_id, content, kind, source)
   values (auth.uid(), '<anna-id>', 'Anna had a tough week at work', 'recent_event', 'user');
   ```
3. New chat: "anything about Anna I should remember?"
4. Assistant should mention the recent event

### Test 3: Companion mode

Open Fly logs in another terminal: `flyctl logs -a my-assistant-backend`

Send these messages in new chats:

- "I'm exhausted, just had the worst day" → log shows `mode=listener`
- "Help me plan my Q3 strategy across 3 product lines" → log shows `mode=strategist`
- "I think everyone hates me" → log shows `mode=challenger`
- "hai" → log shows `mode=None` (too short)
- "apa itu Docker?" → log shows `mode=practical` (short-circuit, no Haiku call)

Reply style should noticeably differ:
- **listener**: short, validating, asks if you want input
- **strategist**: structured, options/steps
- **challenger**: honest pushback, doesn't blanket-validate the distortion

## Performance impact

- Mode detection adds ~500ms Haiku call **but runs in parallel** with other context fetching. Net latency increase: 0-200ms (worst case when mode call is the slowest in the parallel batch).
- Short-circuit triggers on messages <30 chars OR containing obvious "practical" hints — saves the Haiku call entirely on those.
- Cost: ~$0.0001 per qualifying message. Negligible.

## Honest notes

- **Mode misclassification will happen.** Haiku is fast but not perfect. The directive is a hint, not a hard rule — Claude can still reply naturally if the mode doesn't fit. Worst case: a strategist reply when listener was needed, recoverable in the next turn.
- **No frontend exposure of mode.** Per request: invisible to user. If we want to expose ("Claude is in listener mode"), that's trivial later — current architecture already returns it via the log.
- **`practical` short-circuit is rough.** It catches obvious "what is" / "how do" patterns but won't catch all practical questions. The full classifier picks up the rest.
- **No caching across turns.** Mode is re-detected every message because user state shifts. Could cache for ~30s if cost ever matters; it doesn't yet.
- **Notes rendering caps at 3 per person, 140 chars each.** Prevents prompt bloat when a person has 50 historical notes.

## What's NOT in this zip

Per the audit reply: skip face recognition, romantic boundaries, FSM, "loneliness/dopamine layer" — those are either out of scope or marketing speak.

Also skipped: chat-based inferred emotional extraction. The ChatGPT prompt asked for this; I left it out because:
- It's risky — over-extraction creates noise in `emotional_state` table
- Current data path (journal) is high-signal, intentional, and self-reported. Adding chat inference dilutes that signal
- If we add it later, it needs careful filtering (only on emotionally explicit user statements like "I'm exhausted", "I'm so excited"), confidence < 0.7, and never overwrites self_report

If you want this later, it's a focused 1-file addition — not bundled here so as not to break the conservative emotional-state behavior.
