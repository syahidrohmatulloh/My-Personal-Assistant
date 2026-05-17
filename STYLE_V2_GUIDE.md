# Style Profiles — Rich v2 (texture-aware)

Fixes the "hambar" problem: style adaptation only adjusted high-level tone
(warmth, formality) without capturing actual texting texture. v2 extracts
concrete patterns + literal verbatim exemplars and injects them as anchors
in the system prompt, with explicit override of baseline polish.

## What changes

**Backend:**
- `app/services/style_extractor.py` — new v2 `StyleProfile` schema:
  - Replaces abstract scales (`warmth_level: "warm"`) with concrete patterns (`message_shape`, `sentence_style`, `punctuation_habits`, `fillers_and_softeners`, `capitalization`, `emoji_pattern`, `affection_style`, `teasing_style`, `initiation_pattern`, `response_tendency`)
  - Adds `exemplars` — 5-12 literal verbatim short messages from the source person
  - `compact_directive` now ~60-150 words with specific fillers + cadence (was ~1 sentence)
  - Adds `schema_version: 2` flag
- `app/routers/chat.py` — schema-aware directive renderer:
  - v2 renderer: exemplars block + concrete patterns + explicit override of "polished AI register"
  - v1 renderer: legacy fallback with smaller block + suggestion to re-analyze
  - Either way: hard safety rails (no identity claim, no quoting back verbatim, do_not_copy list)
- `max_tokens` bumped 3000 → 4000 for richer Haiku output

**Frontend (`app/settings/style-profiles/page.tsx`):**
- Preview step shows new v2 fields + dedicated "Style anchors (verbatim)" block
- ProfileDetails auto-detects v1 vs v2, renders appropriate field set
- "Legacy format" badge on old profiles
- Falls back gracefully to v1 layout if a profile lacks v2 fields

No SQL changes — `extracted_style` is jsonb, schema is backward-compatible at the DB level.

## Migration

Per your choice: **migrate by re-analyze**.
- Old profiles (v1) still work — fall through legacy renderer, show "Legacy format" badge
- To upgrade: delete the old profile + create a new one with the same transcript. ~5 min per profile.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/style-v2/. .
```

## Deploy

```
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Style v2: rich texture + exemplars" && git push
```

## Test

### 1. Re-analyze your Putri Kasturi profile
- Settings → Style Profiles → delete the Putri Kasturi profile
- Click New → upload same .txt → Continue → pick Putri Kasturi → Analyze
- Preview should now show:
  - **Style directive** — 60-150 words with specific fillers + cadence
  - **Style anchors (verbatim)** — 5-10 literal short messages from her
  - Fields like Message shape, Punctuation, Fillers, Affection, Teasing
- Save

### 2. Test in chat
- New chat → pick the new Putri Kasturi profile
- Ask something casual ("apa kabar")
- **Expected difference vs v1:**
  - Reply should be fragmented (multiple short messages-feel) if she chats that way
  - Lowercase if she does
  - Should drop in fillers naturally (sih, yaa, wkwk — whatever was extracted)
  - Should NOT feel like polished AI with a warm coat of paint
- Ask something supportive ("aku lagi capek nih")
  - Reply should match her actual support pattern (practical first vs emotional first)

### 3. Check Fly logs for directive size
```
flyctl logs -a my-assistant-backend
```
Look for the chat handler invocation. Prompt should be noticeably larger when v2 style is active (~500-800 more chars from exemplars + override block).

## Honest notes

- **v2 is more recognizable but not perfect.** Claude is still a model — it can be told "use 'sih' naturally" and overuse it on first try. Texture improves over a few turns as it calibrates.
- **Exemplars carry actual content** from your transcript into the system prompt. They're not stored in chat history (system prompt is ephemeral per turn). But they ARE in the DB row `extracted_style.exemplars`. If you want them auto-redacted, that's a follow-up.
- **`do_not_copy` extraction is conservative-ish.** Haiku decides what's "private/sensitive" based on the prompt. Review on save — if you see something there that shouldn't leak, delete the profile and skip that part of the transcript.
- **Override rule explicit in prompt:** "If their style is fragmented, send fragmented short replies — not one balanced paragraph." This intentionally overrides the BASE_PROMPT's anti-fragmentation rule for THIS conversation only.
- **Skip the requested "intensity slider" (subtle/balanced/strong).** Reasoning: 3 modes means 3x prompt variation to maintain. "Strong by default" with the option to switch to Default-style if the user wants a polished tone is simpler and tested.
- **Skip automatic eval tests.** Cadence similarity tests require human judgment or a much more expensive model. Look at actual chat replies vs transcript — that's the only honest signal.

## What if reply still feels generic

Diagnostic order:
1. Check the saved profile in Settings → click "Show full profile". Are `exemplars`, `fillers_and_softeners`, `punctuation_habits` populated with specific content (not "unclear")? If "unclear", re-analyze with more transcript.
2. Check Fly logs at the moment of reply. Search for `style=style_profile:` — if it's `style=default`, the profile isn't attached to the conversation. Use sidebar 3-dot → Change style.
3. If everything looks attached but reply still feels generic: paste a sample reply + a snippet of the original transcript here. Then we know whether the model is failing to imitate (model limitation) or whether the extractor missed the texture (extractor problem).
