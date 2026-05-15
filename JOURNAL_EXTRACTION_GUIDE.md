# Journal → structured extraction

Existing journal already extracts `life_events`. This adds two more extraction
targets from the same journal text:

1. **Relationship notes** — when the journal mentions a registered person by
   name, write a note to `relationship_notes` linked to that person.
2. **Goal check-ins** — when the journal references an active goal (by title
   substring), write a `goal_check_ins` row capturing momentum + note.

Both writes are **inferred** with `confidence=0.7`, never `self_report`.
Both refuse to create new people or goals — we only ever attach to ones
the user has registered. No fabrication.

One Haiku call extracts both at once.

## Apply

```
cd ~/my-assistant
cp -R ~/Downloads/journal-extraction/. .
```

No SQL changes. Pure backend code.

## Deploy

```
cd ~/my-assistant/backend
flyctl deploy
```

## Test

Prereq: Have at least one person added in `/people` and one active goal in
`/goals`. Without these, extraction has nothing to attach to.

1. Add a person (e.g. "Anna", relationship "wife") in `/people`.
2. Add an active goal (e.g. "Ship the assistant by EOQ") in `/goals`.
3. Write a journal entry mentioning both: *"Long day. Talked to Anna about
   how the assistant is coming along — she thinks the demo's almost there."*
4. Wait ~5 seconds (Haiku call + writes).
5. In Supabase:
   - `relationship_notes` should have a row linking the user to Anna with
     `content` about the discussion, `kind=recent_event`, `source=inferred`.
   - `goal_check_ins` should have a row for the assistant-launch goal with
     a `note` about demo progress.
6. Fly logs: `journal P&G extraction: user=... people_notes=1 goal_check_ins=1`

## What it explicitly will NOT do

- It will NOT create a new person if you write *"talked to Sarah today"* and
  Sarah isn't registered. It will skip + log it.
- It will NOT create a new goal if you mention progress on something not
  registered.
- It will NOT promote inferred notes to self-reported. Confidence stays 0.7
  forever unless you edit them manually.

This is by design — Principle 3 (user-authored truth dominates inferred truth).

## Honest notes

- Goal-matching uses substring (case-insensitive). If you have two goals
  whose titles overlap, the first one in the list wins. Edge case; revisit
  if you hit it.
- People-matching uses exact name (case-insensitive). Nicknames or partial
  references won't match. That's deliberate — saving notes to the wrong
  person is worse than missing a match.
- Person extraction can cost ~$0.001 per journal entry. At one entry per
  day, ~$0.03/month. Negligible.
