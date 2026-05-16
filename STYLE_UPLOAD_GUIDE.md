# Style Profiles — Upload + Sender Detection

Adds three things on top of the existing style profiles feature:

1. **.txt file upload** in the Settings UI (paste still works as fallback)
2. **`POST /style-profiles/preview-parse`** endpoint — detects senders, flags which ones look like the current user, recommends the non-user target
3. **Stratified sampling** for the Haiku analyze call — beginning + middle + recent chunks instead of one head-of-transcript slice. Auto-tunes between 12k and 30k chars based on transcript size.

## Files changed

**Backend:**
- `app/services/style_parser.py` — adds `is_likely_user()`, `summarize_senders()`, `recommend_target()`
- `app/services/style_extractor.py` — replaces `_format_transcript` with `_build_stratified_sample` + `_build_plain_sample`; adds `_auto_budget` heuristic; `extract_style` now accepts user context + returns `warnings`
- `app/routers/style_profiles.py` — adds `POST /preview-parse`; `POST /analyze` now accepts `current_user_name`, `current_user_email`, `current_user_aliases`; loads user identity from DB as fallback; enforces 5MB cap

**Frontend:**
- `lib/api.ts` — adds `previewParseStyle()`, `PreviewSender`, `PreviewParseResult`; extends `AnalyzeResult` with `warnings`
- `app/settings/style-profiles/page.tsx` — replaces single form with 3-step wizard (Input → Sender → Preview)

No SQL changes. No new dependencies.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/style-upload/. .
```

## Deploy

```
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Phase 4.11: upload + sender detection + stratified sampling" && git push
```

## Test flow

### 1. Upload .txt
- Settings → Style Profiles → New
- Click "Upload .txt" → pick a WhatsApp/Telegram export
- Filename appears as a chip; transcript loaded into textarea (visible char count)
- Or paste manually

### 2. Sender detection
- Click "Continue" → ~1-2 sec (no Haiku call, just parsing)
- Sender list appears with badges:
  - "Recommended" — the most-active non-user sender
  - "Likely you" — senders matching your identity name/email/aliases
- Default selection is the recommended one (NOT you, even if you have more messages)
- Optional: "Treat entire text as one writing sample" if you don't want sender split

### 3. Analyze
- Click "Analyze style" → ~3-8 sec (Haiku call with stratified sample)
- Preview shows extracted style + warnings
- Common warnings:
  - "Only N messages analyzed — extracted style may be less reliable" (sparse target)
  - "Transcript format wasn't recognized…" (plain text fallback)
  - "The selected sender looks like your own messages…" (user override of recommendation)
- Edit profile name → Save

### 4. "Pick different sender" loop
- From preview step, click "Pick different sender" → back to confirm step with original parse intact
- No need to re-upload

## Honest notes

- **User detection is heuristic.** It catches name matches, email handle, "Me"/"Saya" labels. False positives possible if your contact's name contains yours (e.g. "Anna Rohmatulloh" — same last name). Counter via explicit selection.
- **Backend loads `user_identity.profile.name` if frontend doesn't send it.** Frontend currently doesn't auto-send user context — it relies on backend lookup. Works fine as long as you've filled in identity at /identity.
- **5MB cap is enforced** both client-side (rejects upload) and server-side (rejects request). Above 5MB you get a friendly error.
- **Auto-tune budget reasoning:**
  - ≤20 target msgs OR ≤8k total chars → 12k budget (no point sending more)
  - ≥50 target msgs OR ≥40k total chars → 30k budget (capture variety)
  - In between → linear scale
- **Stratified sample = beginning 30% + middle 30% + recent 40%.** Recent gets more because current style matters most.
- **Plain text fallback** uses 3-chunk split too (begin/mid/end), no sender labels.
- **No raw transcript persistence anywhere.** Both preview-parse and analyze process in memory and discard.
- **Error surfacing:** previously failed analyses returned generic 422. Now backend returns specific reason in `warnings[0]`; frontend shows it in the error banner. Cases like "Haiku timeout" or "schema mismatch" are visible.

## What's NOT in this zip

- Frontend passing user identity explicitly (Phase 5+, when we may pass it for memory hint too)
- Re-analyze with different sender BUT new transcript (current "Pick different sender" only re-picks within same parse). Reload page to start over.
- Multi-file upload + merge — out of scope, paste multiple chats together if needed.
