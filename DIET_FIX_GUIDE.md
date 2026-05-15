# Diet plan & cold-start fix

Three issues, one zip:

1. **Fly auto-stop ON** — caused machines to keep restarting, dropping Supabase HTTP/2 connections mid-request
2. **`RemoteProtocolError` not recovered** — stale connection in singleton client led to "Error terjadi" in chat bubble
3. **Diet plan tidak ke-memo** — conversation < 4 messages didn't trigger summary, and assistant-provided plans never enter `memories` table

## What changed

**A. fly.toml**
- `auto_stop_machines = false`
- `min_machines_running = 1`
- (these were in the perf zip but didn't actually deploy in your production)

**B. supabase_client.py** — adds `reset_supabase()` and `safe_execute()` helper that:
- Catches `RemoteProtocolError`, `ConnectError`, `ReadError`, `WriteError`, `PoolTimeout`
- Resets the cached client (drops the dead HTTP/2 socket)
- Retries the call once

**C. chat router** — hot-path supabase calls (ownership check, save user msg, load history, save assistant msg) now run through `safe_execute`. If Fly restarts the machine mid-conversation, the next request auto-recovers instead of returning "Error terjadi".

**D. conversation_summary.py** — minimum threshold dropped from 4 → 2 messages. Short chats with concrete content (like a diet plan) now get summarized.

**E. memory.py extraction prompt** — extended to extract `kind="plan"` for concrete assistant-provided plans the user accepted. Captures the substance (numbers, structure) not just "user got a diet plan".

**F. schema_phase46_plan_kind.sql** — tiny migration to allow `'plan'` in the memories.kind CHECK constraint.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/diet-fix/. .
```

## SQL — run once in Supabase SQL Editor

Paste contents of `backend/schema_phase46_plan_kind.sql`. Idempotent.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Fix: fly auto-stop off, supabase retry, plan extraction, summary threshold 2"
git push
```

**Important — verify fly.toml landed:**

After `flyctl deploy`, run:
```
flyctl config show -a my-assistant-backend | grep -E "auto_stop|min_machines"
```

Should show `auto_stop_machines: false` and `min_machines_running: 1`. If still showing `true`, your local fly.toml may have been overwritten — re-copy from the zip.

## Re-summarize existing diet conversation

The summary threshold change only triggers on **new** messages. To force the diet conversation to get summarized now without sending a new message, in Supabase SQL Editor:

```sql
-- Clear the "summarized_through" marker on your diet chat so the next message triggers summarize.
-- Or, easier: open that chat and send any short message — summary will generate.
```

Easier approach: open the diet chat, send "thanks" — the background summarize will run.

## Test

1. **Cold start fixed:** Wait 10 minutes idle, then open a chat. Should respond within 1-2 seconds (machine stayed running).

2. **Stale connection recovery:** Hard to test without Fly migrating your machine. The Fly log will now show `supabase: transient transport error, resetting client` instead of an exception trace, and the chat will succeed on retry.

3. **Diet plan memory:** Open the diet chat, send "thanks" or any short follow-up. Wait ~5 seconds. Then in Supabase:
   ```sql
   select kind, content from memories
   where user_id = auth.uid() and kind = 'plan'
   order by created_at desc limit 5;
   ```
   Should see the concrete diet plan with numbers/structure.

4. **Cross-chat retrieval:** New chat, ask *"What's my diet plan again?"* — Claude should answer specifically, not generically.

## Honest notes

- The `safe_execute` wrapper only covers the **synchronous chat hot-path**. Background tasks (memory extraction, summarization, title gen) have their own try/except and just skip on failure. If you see them silently fail more often after Fly migrations, we can extend the wrapper to async there too — but for now they're best-effort and recover on the next turn.

- The "plan" extraction depends on Claude understanding what counts as a concrete plan vs. casual advice. Expect ~80% precision in early use. If it over-extracts (creates plan memories for casual chitchat), tune the prompt or raise the dedup threshold.

- Lower summary threshold (2 messages) means more Haiku calls. Cost is ~$0.0005 per summary. Even at 100 short conversations/day = $0.05/day. Acceptable.

- `auto_stop_machines = false` + `min_machines_running = 1` costs ~$2-3/month for the always-on machine. Worth it for a single-user product where cold start UX matters more than $.
