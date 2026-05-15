# Phase 4.5 — Cross-conversation continuity

Conversation-level summarization. After ~10 messages, each conversation gets a
2-4 sentence summary + embedding stored on the `conversations` row. New chats
do a semantic search across these summaries to find related past discussions.

Effect: the assistant can reference what was discussed in *other* conversations,
not just facts extracted into `memories`.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/phase45-summaries/. .
```

## SQL — run once in Supabase SQL Editor

Paste contents of `backend/schema_phase45_summaries.sql`. Adds 4 columns + 1
index + 1 function. Idempotent.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy

cd ~/my-assistant
git add -A
git commit -m "Phase 4.5: conversation summaries for cross-chat continuity"
git push
```

(No frontend changes — entirely backend.)

## Test

1. Have a substantive chat — 6+ turns on some topic (e.g. "thinking about taking a new job").
2. Wait a minute. In Supabase Table Editor → `conversations`, find that row.
   `summary`, `summary_embedding`, `summarized_at` should all be populated.
3. Start a *new* chat. Ask something topically related (e.g. "any new thoughts on the career thing?").
4. Backend log line should show `related_summaries=1` (or more).
5. Claude's reply should reference the prior conversation naturally.

## What it does NOT do

- Doesn't re-summarize on every turn — only when a conversation has grown by
  ≥10 messages since last summarize. Cheap.
- Doesn't dump summaries verbatim into the prompt — they're wrapped with
  *"for grounding, not for recital"* per your anti-repetition doctrine.
- Doesn't search past summaries when current conversation has <2 messages —
  not enough query signal for meaningful matching.

## Honest notes

- Threshold for relevance is 0.55 cosine similarity. Lower than memory
  retrieval's 0.5 because summaries are richer text → similarity scores
  cluster lower. Tune later if you see noise.
- Haiku call adds ~1s after stream finishes but runs in background — user
  doesn't wait.
- Summary embeddings live in `conversations.summary_embedding`. ivfflat
  index with `lists=10` because typical users have <100 summarized chats.
  Revisit if you exceed 500.
