# Style Profiles UI (Zip 2 of 2)

Frontend UI for Conversation Style Profiles. Apply AFTER backend zip 1 and
rollback zip are deployed.

## What's new

**Frontend (new):**
- `app/settings/page.tsx` — Settings landing page (currently one section: Personalization)
- `app/settings/style-profiles/page.tsx` — Full management page: list, create, preview, save, rename, delete
- `components/chat/conversation-style-badge.tsx` — Small floating indicator + picker in the chat header

**Frontend (modified):**
- `lib/api.ts` — adds style profile API functions, extends `createConversation` to accept `styleProfileId`, extends `Conversation` type
- `middleware.ts` — adds `/settings/*` to protected routes
- `components/chat/sidebar.tsx` — adds `Settings` link in footer; adds optional dropdown next to "New chat" button (only shown when user has ≥1 profile); adds **"Change style"** in conversation 3-dot menu
- `app/chat/[id]/page.tsx` — renders the style badge in chat header

## What it does

1. **Settings → Personalization → Conversation Style Profiles** in sidebar footer
2. **Paste WhatsApp/Telegram/plain text** → click Analyze → preview extracted style → name it → save
3. **Sidebar "New chat" button**: stays exactly as before by default
4. **When user has ≥1 saved profile**: small chevron appears next to "New chat" → dropdown → pick style at creation
5. **Existing conversations**:
   - Style badge in top-right of chat area shows current style ("Default" / profile name)
   - Click badge → picker → switch style OR roll back to Default
   - Same picker also accessible via sidebar conversation 3-dot menu → "Change style"
6. **Default users (no profiles created)**: chat UI is 100% unchanged — badge hidden, dropdown hidden

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/style-ui/. .
```

No SQL changes. No new dependencies.

## Deploy

```
cd ~/my-assistant
git add -A
git commit -m "Phase 4.11 Zip 2: Style profiles UI"
git push
```

Vercel auto-deploys. No backend changes — Fly redeploy not needed.

## Test flow

### 1. Settings link
- Open sidebar → footer should show new "Settings" link
- Click → Settings page → click "Conversation Style Profiles"

### 2. Create your first profile
- Click "New"
- Paste a chat sample (5+ messages from one person works best)
- Optionally set target name (defaults to most-frequent sender)
- Click "Analyze style" → wait 2-4 sec
- Preview shows: style summary + key attributes + any do_not_copy items (red box)
- Edit profile name, click "Save profile"

### 3. Use in new chat
- Sidebar "New chat" now has a small chevron next to it
- Click chevron → dropdown: "Default" + your profiles
- Pick → new chat opens with style attached
- Send message → reply reflects style
- Fly logs: `style=style_profile:abc12345`

### 4. Switch style on existing conversation
**Via badge:** open the chat → top-right pill ("Default" or profile name) → tap → picker.
**Via sidebar:** conversation row → 3-dot menu → "Change style".

### 5. Rollback to Default
Picker → pick "Default". Or just start a new chat with the main button (always Default).

## Honest notes

- **Badge appears for every conversation IF user has ≥1 profile saved.** Hidden entirely if no profiles exist. Default users' UI is 100% unchanged.
- **Style switch applies to NEXT message, not retroactively.** Existing messages were generated under the old style.
- **Mobile UX**: badge is positioned at top-right. If it overlaps with the mobile topbar on narrow screens, kasih tahu and I'll adjust positioning.
- **Profile delete cascades safely** via `ON DELETE SET NULL` — conversations using a deleted profile auto-rollback to Default.

## What's NOT in this zip

- Profile sharing or templates
- Bulk apply to multiple conversations
- Re-analyze with new transcript (delete + recreate is the workflow)
