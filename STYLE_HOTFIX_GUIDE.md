# Style profiles — UI + extractor hotfix

Fixes 2 bugs reported via screenshot on the sender selection step:

1. **Sender selection not visible.** Putri Kasturi was auto-selected as Recommended, but the `border-accent` highlight was nearly invisible in dark mode — clicking did nothing visually even though state was changing.
2. **"Style analysis was incomplete"** on 5249-message transcript. Not actually about message count — Haiku's output exceeded Pydantic field caps (40-120 chars per field) for a complex profile, and `max_tokens=2000` was occasionally truncating the JSON.

## Fixes

**Frontend (`app/settings/style-profiles/page.tsx`):**
- `SenderOption` now has `border-2` + `ring-2 ring-accent/20` on selected state, plus an explicit radio-dot indicator on the left. Visible.
- Same treatment for the "Treat entire text" option.

**Backend (`app/services/style_extractor.py`):**
- `StyleProfile` Pydantic constraints loosened (display_name 80→200, levels 40→120, styles 120→300, common_phrases 10→20 items, compact_directive 500→800).
- Optional string fields default to `""` instead of being required.
- `max_tokens` 2000 → 3000 — gives Haiku room to return full profile.
- New `_trim_profile_fields()` runs BEFORE Pydantic validation: truncates over-cap strings, fills missing required strings with "unclear", filters non-string list items. Single field overflow no longer kills the whole profile.
- Better error logs: stop_reason logged when max_tokens hit; ValidationError now shows which fields failed.
- More specific user-facing message when validation still fails.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/style-hotfix/. .
```

## Deploy

```
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Style hotfix: visible selection + loose constraints" && git push
```

## Verify

1. Reload `/settings/style-profiles`, upload your 5249-message transcript again
2. Click "Continue" → sender list. **Putri Kasturi should now show a filled radio dot on the left + thick accent border.**
3. Click between senders — selection moves visibly.
4. Click "Analyze style" → should succeed with the new larger budget + 3000 tokens.
5. If it still fails: open `flyctl logs -a my-assistant-backend` during the click — log line will say which field failed. Paste the log; root cause is now visible.

## Why this fix is conservative

I didn't:
- Reduce the LLM transcript budget — that would lose signal
- Switch to a stricter prompt — Haiku's output drift is real, schema flexibility is the right place to absorb it
- Add a retry — the issue isn't transient, it's deterministic per Haiku output

I did add belt-and-suspenders: truncate at the dict layer + defaults at the Pydantic layer. Either alone would catch most cases; both together catch all.
