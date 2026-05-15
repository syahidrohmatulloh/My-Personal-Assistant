# Mobile polish — apply

Conversational-experience pass focused on mobile. No new SQL, no new env vars,
no new dependencies.

## What changed

**Layout & viewport:**
- `100dvh` / `100svh` replaces `100vh` — fixes "composer hidden behind iOS Safari URL bar"
- `viewport-fit: cover` + `env(safe-area-inset-*)` — respects notch & home indicator
- `maximumScale: 1` — stops iOS auto-zoom on input focus
- `pb-safe`, `pt-safe`, `pl-safe`, `pr-safe` utilities for safe-area padding

**Sidebar → drawer on mobile:**
- Desktop unchanged (256px rail)
- Mobile: fixed topbar with hamburger; sidebar slides in as drawer over content
- Body scroll locked while drawer open
- Tap outside / tap conversation closes drawer
- 85vw drawer (capped at 300px), respects safe-area

**Input ergonomics:**
- Input font-size 16px on mobile (prevents iOS auto-zoom)
- Tap targets 40px+ on mobile (Apple HIG minimum)
- `enterKeyHint="send"` shows "Send" key on mobile keyboards
- `autoCapitalize`, `autoCorrect`, `spellCheck` enabled
- On mobile, Enter = newline (taps Send button explicitly); on desktop, Enter = send

**Scroll smoothness:**
- Auto-scroll only when user is within 120px of bottom (won't yank them back if they scrolled up to read)
- Instant scroll during streaming (smooth fights rapid updates and feels laggy)
- "Jump to latest" pill appears when user has scrolled up; tap to return
- `-webkit-overflow-scrolling: touch` for iOS momentum scrolling on inner containers

**Spacing rhythm:**
- Message bubbles wider on mobile (92% vs 78% desktop) — less wasted space
- Bubble padding tighter on mobile (px-3.5 py-2.5 vs px-4 py-3)
- Vertical page padding tightens on mobile (py-5 vs py-8)
- Composer padding tightens on mobile (px-3 vs px-6)

**Performance:**
- Ambient orbs smaller and less-blurred on mobile (blur 48px vs 80px) — easier on Android GPUs
- `prefers-reduced-motion` disables orbs and animations entirely
- `touch-action: manipulation` on all interactive elements — no 300ms tap delay

**Visual:**
- `theme-color` meta tag for browser chrome (matches bg in light/dark)
- Mobile topbar uses glass treatment matching the rest of the design
- Drawer enter animation is iOS-style (cubic-bezier(0.32, 0.72, 0, 1))

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/mobile-polish/. .
```

## Test on real mobile

Local dev usually doesn't reproduce the keyboard / safe-area / dvh issues. Test on actual phone:

1. Start dev server with explicit host:
   ```
   cd ~/my-assistant/frontend
   npm run dev -- --hostname 0.0.0.0
   ```
2. On phone, open `http://<your-laptop-ip>:3000` (both devices on same Wi-Fi)
3. Sign in, open a conversation
4. Tap input — keyboard slides up, composer should stay visible above it
5. Type a long message, send — assistant streams without page jumping
6. Scroll up during streaming — "Jump to latest" pill appears
7. Open menu — drawer slides in over content, tap outside to close
8. Rotate device — no layout shift

## Deploy

```
cd ~/my-assistant && git add -A && git commit -m "Mobile polish: drawer, dvh, safe-area, smart scroll" && git push
```

No backend changes — Fly deploy not needed.

## Files changed

- `frontend/app/globals.css` — viewport units, safe-area, reduced-motion, mobile orbs, drawer animation
- `frontend/app/layout.tsx` — viewport meta export (Next 15 syntax)
- `frontend/app/chat/chat-shell.tsx` — dvh container, mobile topbar offset
- `frontend/app/chat/page.tsx` — text sizing
- `frontend/app/chat/[id]/page.tsx` — smart auto-scroll, jump-to-latest pill
- `frontend/components/chat/sidebar.tsx` — mobile drawer mode
- `frontend/components/chat/composer.tsx` — keyboard handling, safe-area, 16px font
- `frontend/components/chat/message-bubble.tsx` — mobile spacing
- `frontend/app/{identity,goals,people,memories,journal}/page.tsx` — min-h-dvh + tighter py
- `frontend/app/{login,signup,welcome}/page.tsx` — min-h-dvh, tighter padding

## Honest caveats

- iOS Safari's keyboard behavior is famously finicky. `100dvh` is the right modern fix and works in iOS 15.4+, but very old Safari may still show the "composer hidden" bug. If that's a real audience for you, we add a `visualViewport` API listener as a fallback — but it's tricky code and I don't recommend it unless you actually see the bug.
- Auto-zoom prevention via `maximumScale: 1` is the standard fix. Some accessibility audits flag it as it prevents user pinch-zoom on the whole page. Tradeoff is real; we prioritized the conversational experience.
- Drawer is JS-controlled (open state). For a more sophisticated app you'd add gesture-driven dismiss with `@radix-ui/react-dialog` or similar. Overkill for now.
