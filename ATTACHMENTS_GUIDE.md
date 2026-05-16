# Vision + PDF upload (Phase 4.9)

Adds multimodal capability: photos and PDFs can be attached to chat messages.
Claude sees them via vision API. Photos also get auto-described by Haiku
in the background → description saved as a `memory` so the assistant
"remembers" the image in future chats.

## What's new

**Backend:**
- `schema_phase49_attachments.sql` — `message_attachments` table + private Storage bucket
- `app/services/storage.py` — Supabase Storage helpers
- `app/services/attachments.py` — magic-byte MIME detection, validation, Claude content block builder, auto-describe via Haiku
- `app/routers/attachments.py` — `POST /attachments/upload` (multipart)
- `app/routers/chat.py` — wires attachments into the user message as multimodal content blocks
- `app/schemas/__init__.py` — `ChatIn` gains `attachment_ids: list[str]`
- `app/main.py` — registers the attachments router

**Frontend:**
- `lib/api.ts` — `uploadAttachment()` with Canvas-based image resize to 1568px max + JPEG 80%
- `components/chat/composer.tsx` — paperclip button, file picker, attachment chips with upload status
- `app/chat/[id]/page.tsx` — passes attachment IDs to `streamChat`

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/attachments/. .
```

No new dependencies — `python-multipart` already in pyproject.toml.

## SQL — run once in Supabase SQL Editor

Paste contents of `backend/schema_phase49_attachments.sql`. Creates the table AND the Storage bucket.

**Verify the bucket exists:** Supabase dashboard → Storage → should see `attachments` bucket marked as Private.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Phase 4.9: vision + PDF attachments"
git push
```

## Test

1. **Upload photo:** Open a chat. Tap paperclip. Pick a photo. Chip appears with spinner → done check. Type "what's in this?" and send.
   - Claude should respond about the actual image content.
   - Wait ~5s. Check Supabase `memories` table → should see a new row like `"User shared an image: <description>"` with `source='auto'`, `kind='context'`.

2. **Cross-chat recall:** Open a new chat. Ask "what did I upload to you recently?" → Claude should reference the photo description.

3. **PDF upload:** Pick a PDF (<10MB). Send with "summarize this". Claude reads + answers.

4. **Image resize verification:** Open browser DevTools → Network tab. Upload a large photo (>5MB original). The upload request payload should be <1MB.

5. **Magic-byte validation:** Try renaming a `.txt` file to `.jpg` and uploading. Backend should reject with 400 — wrong magic bytes.

## Limits

- Max **10 attachments per message**
- Max **10MB per file** (raw, before resize)
- Images auto-resize: max 1568px long side, JPEG 80% — typically ends up <500KB
- PDFs: max 100 pages (Claude's hard limit), 10MB
- Accepted: JPEG, PNG, GIF (no animation preserved when resized), WebP, PDF

## Architecture choices

**Why server-side resize + magic bytes?**
Frontend resize is good UX (instant feedback, less bandwidth), but never trusted.
We re-validate MIME via magic bytes on backend because the Anthropic API rejects mismatched media_type / content with 400 errors.

**Why store files in Supabase Storage, not base64 in Postgres?**
A 5MB image becomes ~6.7MB as base64. Inline in a TEXT column blows up message table size, slows every SELECT. Files stay separate; metadata table only.

**Why describe images automatically?**
Without it, an uploaded image is just bytes on disk — Claude can see it during that turn but forgets it after. Description saved as memory means "ingat foto" actually works across chats.

**Why "(shared an attachment)" placeholder when text is empty?**
Claude's API requires at least one text block in user content. Pure-image messages would otherwise fail. Placeholder is innocuous and the actual image is always present.

## Honest caveats

- **Image describe runs in background** — first chat with an image doesn't have it in memory yet. Subsequent chats do.
- **No attachment preview in message bubble yet.** Attachments are saved + linked to messages, but the bubble UI doesn't render thumbnails of past attachments. Adding that is a separate small task — message-bubble.tsx would need to query attachments for each message. Skipped because it's mostly cosmetic and doesn't affect Claude's ability to see them.
- **Storage costs are real.** Supabase free tier = 1GB Storage. At ~500KB/photo, that's ~2000 photos. Monitor in dashboard. Old attachments cleanup script not included — defer until needed.
- **Face recognition not included.** Per our decision: vision passive only. Claude sees the photo in real-time and describes it; no facial embeddings stored.
- **Frontend resize on iOS Safari** uses Canvas API which works but has quirks on very large photos (>50MP). 99% of photos will resize fine.
