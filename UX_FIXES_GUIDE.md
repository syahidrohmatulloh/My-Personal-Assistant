# Sidebar UX + title fixes

Three things addressed in one zip:

1. **Sidebar "scrolls away" bug** — defensive flex height locking
2. **Chat History header + time grouping** (Today / Yesterday / Previous 7 days / Older)
3. **Auto-rename delay** — invalidates list 4s after stream so background Haiku title gen lands
4. **Bonus:** `highlight.js` moved to runtime deps in `package.json` so Vercel doesn't fail. You can stop maintaining your `sed` workaround.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/ux-fixes/. .
cd frontend
npm install   # picks up highlight.js as a runtime dep
```

After apply, you can revert your local `sed` patches if you want — `globals.css` import is restored, and `Providers` is back to named export. (Your default-export version of `providers.tsx` still works if you prefer to keep that.)

## What changed

**chat-shell.tsx** — added `overflow-hidden` to outer flex container + `min-h-0` to content wrapper. Stops the flex children from growing past viewport (which was making the whole page scroll instead of the inner panels).

**sidebar.tsx** —
- Added `shrink-0` to header / new-chat button / footer (locks their heights)
- Added `min-h-0` to conversation list so it can shrink and scroll independently
- Added `min-h-0` + `overflow-hidden` to the desktop `<aside>` itself
- New "Chat History" small caps label between New chat button and list
- Conversations now grouped by Today / Yesterday / Previous 7 days / Previous 30 days / Older

**chat/[id]/page.tsx** — title invalidation delayed 4s after stream finishes (server-side Haiku call needs time to complete).

**package.json** — `highlight.js` moved from devDependencies → dependencies.

## Deploy

```
cd ~/my-assistant
git add -A
git commit -m "Sidebar UX: fixed height, history header, time grouping, title delay"
git push
```

No backend changes — Fly deploy not needed.

## Honest notes

- Time grouping uses `updated_at` (which the chat router bumps on every message). So a 2-week-old conversation you replied to today shows as "Today". That matches ChatGPT/Claude.ai behavior and is what users expect.
- The 4-second invalidation delay is a pragmatic fix. The cleaner solution is server-sent events that include a "title updated" event, but adding bidirectional events to streams adds complexity not justified at this scale.
- If you ever see a conversation stuck on "New chat" after the 4s window, it means the Haiku call failed. Check Fly logs for "title generation failed" warnings — typically a transient API issue, retry by sending another message in that conversation.
