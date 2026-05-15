# Scroll fix — apply

Two bugs from the previous UX zip:

1. **Sidebar disappears** on some desktop configurations (after `overflow-hidden` was added to chat-shell)
2. **Stuck at bottom, can't scroll up** when opening a long conversation

## Root cause

The combination of `overflow-hidden` on the flex parent + `scrollIntoView` API in the conversation page was scrolling the wrong ancestor (sometimes the viewport instead of the inner chat container). And the desktop sidebar's `h-full` was getting consumed weirdly inside the new overflow-hidden parent on some browsers.

## What changed

**chat/[id]/page.tsx** — replaced all `scrollIntoView` calls with direct `element.scrollTop` manipulation against the specific scroll container. Deterministic. Cannot scroll the wrong ancestor.

**sidebar.tsx (desktop aside)** — explicit `h-[calc(100dvh-1rem)]` + `sticky top-2` instead of `h-full`. Browser no longer has to infer height from the flex parent — it's stated outright.

**main element** — added `min-h-0` to the conversation page's `<main>` to ensure flex children can shrink, plus `overscroll-contain` on the scroll container so scroll energy doesn't leak to outer page.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/scroll-fix/. .
```

No `npm install` needed. No backend changes.

## Test

1. Open a long conversation from the sidebar. Should land at the latest message but you can scroll up freely.
2. Sidebar is visible on desktop and stays where it is when you scroll the chat.
3. Send a message during a long conversation — auto-follows the stream. Scroll up during streaming — "Jump to latest" pill appears.
4. Tap "Jump to latest" — smooth scroll to bottom.

## Deploy

```
git add -A
git commit -m "Fix: deterministic scroll, sidebar height locking"
git push
```

## If issues remain

If the sidebar still disappears at certain viewport sizes, paste me the screenshot + your browser window width (DevTools → toggle device toolbar, top-left shows dimensions). Most likely cause then is browser zoom — `Cmd+0` to reset zoom.
