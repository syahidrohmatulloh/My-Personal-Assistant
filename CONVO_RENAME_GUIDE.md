# Conversation rename

## What's new

**Backend:**
- `PATCH /conversations/{id}` — manually set title (durable, won't be overwritten)
- `POST /conversations/{id}/regenerate-title` — re-run Haiku title-gen on demand (for backfilling old "New chat" titles)

**Frontend:**
- 3-dot menu on each conversation row (mobile: always visible, desktop: hover)
- **Rename** → inline input, Enter to save, Escape to cancel
- **Auto-rename** → calls regenerate-title, shows spinner while running
- **Delete** → existing function moved into menu

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/conversation-rename/. .
```

No SQL changes. No new dependencies.

## Deploy

```
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Conversation rename + regenerate title" && git push
```

## Test

1. Sidebar: hover a conversation → 3-dot menu icon appears (mobile: always visible).
2. Click 3-dot → menu with Rename / Auto-rename / Delete.
3. **Rename:** click → inline input → type → Enter saves, Escape cancels.
4. **Auto-rename:** click → spinner shows on row → ~2 sec later, new title appears.
5. For old conversations stuck at "New chat" or "Untitled": just click Auto-rename.

## Honest notes

- **User-renamed titles are durable.** They won't be auto-overwritten by background title-gen on next message. The chat router's auto-title only fires on first turn (`is_first_message`), so manual renames stay.
- **Auto-rename is synchronous** (~1-2 sec Haiku call). User sees the new title immediately. Background regeneration would be invisible — defeats the purpose of an explicit user action.
- **Regenerate needs at least 1 user + 1 assistant message.** Otherwise 400 error — there's nothing to summarize. UI doesn't disable the button; backend just refuses. If you want it disabled in UI for empty conversations, that's a small follow-up.
- **Mobile UX:** 3-dot button is always visible on mobile (no hover). On desktop, it appears on hover. Same pattern as ChatGPT/Claude.ai.
