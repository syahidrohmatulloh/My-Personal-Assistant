# Gap UI — onboarding, goals, people

Fills the Phase 3 UI gaps: guided onboarding, dedicated pages for Goals and People, plus sidebar links.

**No SQL.** Schema sudah ready dari Phase 3.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/gap-ui-files/. .
```

## What's new

**Backend:**
- DELETE endpoints: `/people/{id}`, `/goals/{id}`, `/life-events/{id}`
- Service helpers: `delete_person`, `delete_goal`, `delete_life_event`

**Frontend:**
- `/welcome` — 3-step onboarding (identity → narrative → optional first goal)
- `/goals` — list, create, status changes (achieve/pause/reopen/abandon), delete
- `/people` — list, create with importance + emotional significance + birthday, delete
- Sidebar — Goals & People links added
- Chat layout — auto-redirects new users (empty identity profile) to `/welcome`
- Middleware — protects `/goals`, `/people`, `/welcome`

## Test locally

```
cd ~/my-assistant/backend && uv run uvicorn app.main:app --reload --port 8080
cd ~/my-assistant/frontend && npm run dev
```

**Onboarding flow (use an account without identity, or wipe `user_identity` row):**
1. Sign in → auto-redirected to `/welcome`
2. Step 1: name + communication style
3. Step 2: narrative
4. Step 3: optional first goal (skippable)
5. "Get started" → lands in `/chat`

**Goals:**
1. Click sidebar **Goals**
2. New goal → set horizon + emotional weight → save
3. Hover row to reveal actions (achieve / pause / delete)
4. Filter tabs: active / paused / achieved / abandoned / all

**People:**
1. Click sidebar **People**
2. Add person → name + relationship + importance/emotional sliders + optional birthday
3. Hover row to delete

**Verify retrieval works:**
- Add a goal and a person
- New chat → ask: *"What goals am I working on? Who matters to me?"*
- Claude should reference them (life model context now flowing through prompt builder)

## Deploy

```
cd ~/my-assistant/backend && flyctl deploy
cd ~/my-assistant && git add -A && git commit -m "Gap UI: onboarding, goals, people" && git push
```

## Honest notes

- Onboarding redirect uses chat layout's server-side identity check. Users who skip onboarding can still reach `/chat` directly — they just won't get personalized responses until they fill in Identity later. Skip is intentional.
- Goals UI doesn't yet show check-in history. That comes in Phase 5 (briefings will write check-ins).
- People UI doesn't yet show notes timeline per person. Same reason — Phase 5+ writes there from chat extraction.
- No bulk import. If you have a list of people somewhere, add them manually for now.
