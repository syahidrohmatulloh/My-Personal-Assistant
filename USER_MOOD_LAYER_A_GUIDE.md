# Phase 4.13 Zip 4 Layer A — User mood inference

Adds a USER mood layer that informs tone and support strategy. Completely
separate from companion mood (Aliyya's affect). Read-only on existing tables.

## What's new

**Backend (new):**
- `backend/app/services/user_mood.py` — inference service. Pure-Python on top of `emotional_state` rows. Baseline + delta + causal + evidence + per-message keyword detection.
- `backend/app/services/user_mood_prompt.py` — renders the user mood block for the system prompt. Clearly labeled to NEVER leak into companion mood or UI.
- `backend/tests/test_user_mood.py` — 23 smoke tests, no DB required.
- `backend/apply_layer_a.py` — one-shot patcher for `chat.py`. Idempotent.

**Backend (modified via apply_layer_a.py):**
- `backend/app/routers/chat.py` — 4 surgical patches:
  1. Import `user_mood` + `render_user_mood_block`
  2. Add `user_mood.infer_user_mood(...)` to the parallel asyncio.gather
  3. Extend tuple unpacking
  4. Inject `user_mood_block` into volatile_context (BEFORE companion mood block)

No SQL changes. Reads only from `emotional_state` (already exists since Phase 3).

No frontend changes. No touching `companion_settings`, `companion_mood_state`, or any other table.

## What it does

For each chat turn:

1. Fetches last 30 days of self-reports from `emotional_state` (your existing journal entries land here).
2. Computes:
   - **Latest snapshot** — most recent mood/energy/stress + note + tags
   - **30-day baseline** — rolling mean per axis (needs ≥3 entries)
   - **Delta** — labels each axis as "lower than usual" / "near baseline" / "higher than usual"
   - **Causal context** — regex extracts "karena X" / "because of X" phrases from notes, plus surfaces tags
   - **Evidence** — up to 3 verbatim short snippets from recent notes
   - **Confidence** — weighted score (recency × sample size × DB confidence)
   - **Current-message signal** — keyword detection on the message you JUST typed (free, fast)
3. Renders as a clearly-labeled "## User mood (inferred)" block in the system prompt.

Block always carries hard rules:
- Separate from companion mood
- Use for tone calibration ONLY, never UI ambience or AI affect
- Never recite back as a label ("I see you're stressed")
- User's current message wins over inference

## Architecture safety

User mood ≠ companion mood. Clearly separated at every layer:

| Layer | User mood | Companion mood |
|---|---|---|
| Service | `user_mood.py` | `companion.py` |
| Table | `emotional_state` (read-only) | `companion_mood_state` (managed) |
| Prompt block label | "## User mood (inferred ...)" | "## Companion mood state" |
| Drives ambience? | No | Yes (via meta event) |
| Drives Aliyya's affect? | No | Yes |

The render function explicitly tells Claude: "use to calibrate tone — NOT to drive UI ambience or your own affect."

## Apply

```bash
cd ~/my-assistant
cp -R ~/Downloads/companion-refactor-zip4/. .

# Run the chat.py patcher (idempotent — safe to re-run)
cd backend
python apply_layer_a.py
```

Expected output:
```
Patched app/routers/chat.py:
  + import user_mood services
  + add user_mood.infer_user_mood to asyncio.gather
  + extend tuple unpacking
  + inject user_mood block
```

If you see `ERROR: anchor not found for patch: ...`, it means chat.py was modified since Zip 2 and the anchors don't match. Paste the error and your current chat.py imports + asyncio.gather block; I'll regenerate patches.

## Test (no DB needed)

```bash
cd ~/my-assistant/backend
python tests/test_user_mood.py
```

Expected: `23 passed, 0 failed`.

If pytest installed:
```bash
python -m pytest tests/test_user_mood.py -v
```

## Deploy

```bash
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Phase 4.13 Layer A: user mood inference" && git push
```

## Verify in production

1. **Check startup**:
   ```bash
   flyctl logs -a my-assistant-backend
   ```
   Wait for `Application startup complete`. No ImportError.

2. **Trigger user mood detection — three test cases:**

   **A. With journal data** (you have weeks of entries):
   Send any chat message. Open Fly logs. The system prompt is logged at info level via existing chat log. You won't see the prompt itself, but the chat handler should run with no errors.

   To **directly verify** the block is being computed, run this one-liner in a Python shell connected to your Supabase:
   ```python
   import asyncio
   from app.services.user_mood import infer_user_mood
   from app.services.user_mood_prompt import render_user_mood_block

   ctx = asyncio.run(infer_user_mood("<your-user-uuid>", current_message="lagi capek banget"))
   print(render_user_mood_block(ctx))
   ```

   **B. Test keyword detection** — send Aliyya: "aku capek banget hari ini"
   The prompt will carry a "Current message tone hint: tired" line. Aliyya should pick up on it via tone, NOT by saying "I see you're tired."

   **C. Test no-data fallback** — for a fresh user with zero journal entries, the block should render only the chat keyword signal (or nothing at all). No crash.

## Verify behavior — what you should notice

- **You have recent journal entries showing high stress**: Aliyya's replies should be slightly shorter/gentler. She should NOT explicitly mention your stress unless you bring it up.
- **You type "lagi capek"**: She should respond TO the fatigue (less follow-up questions, calmer pacing), not BY labeling it.
- **You type a normal message after weeks of journals**: Block has baseline + delta. Aliyya calibrates against your typical state, not absolute thresholds.

## Rollback

If anything breaks, the patches are reversible:

```bash
cd ~/my-assistant/backend
git checkout app/routers/chat.py  # revert the 4 patches
rm app/services/user_mood.py app/services/user_mood_prompt.py
flyctl deploy
```

No SQL was changed, no data was written. Rollback is just file-level.

## Honest notes

- **Keyword detection is naive.** "capek banget" hits even if the user is talking about someone else being tired. Acceptable — the signal feeds in as low-confidence ("treat as hypothesis"), so misreads degrade gracefully.
- **Causal regex misses subtler causes.** "Karena X" / "because of X" pattern is conservative. Won't catch "the deadline crushed me today" without "because". Better miss than hallucinate.
- **Baseline needs ≥3 self-reports.** Below that, baseline is hidden — only the latest snapshot is rendered. Avoids misleading deltas from sparse data.
- **Per-request overhead** — one `emotional_state` SELECT (indexed, <30ms typically) added to the parallel gather. Runs concurrently with everything else, so end-to-end latency impact is near zero.
- **Causal pattern only matches Indonesian + English connectors.** If your transcripts are in another language, extraction yields zero — block still renders with latest + baseline + tags.
- **No Haiku.** As requested: no per-message LLM classification. Keyword detection only.
- **No frontend changes.** UI is unchanged.
- **No companion mood touched.** `companion_settings` and `companion_mood_state` are not read or written by this layer.

## What's NOT in this zip

- Mood inference from chat history beyond keyword detection (would need batched Haiku)
- Cached baseline table — pure SQL computed for now
- Frontend visualization of user mood
- Decay function per emotion type (acute vs chronic)
- Updating `emotional_state` rows from chat — only journal writes there
