# M32 — Habit / Routine Learning

**Status:** Implemented by the M32 major patch
**Baseline:** M31G (`a2af6b2`)
**Version:** `M32-v1`

## Purpose

M32 gives Aliyya a conservative, inspectable way to learn recurring routines
from repeated user-authored activity evidence across conversations.

The central rule is:

> Repetition may support an inferred habit, but inference is not user-authored truth.

A one-off event never becomes a habit.

## Boundaries

M32 does not:

- create reminders, calendar events, or goals from inferred habits;
- use an LLM to decide whether a habit exists;
- infer sensitive routines;
- project inferred habits into `user_identity`;
- replace explicit routine statements handled by `memory_intelligence`;
- mutate explicit/manual routine memories;
- create a second `CognitiveDecisionTrace` after the response;
- introduce a new database table or infrastructure service;
- turn M33 consolidation into an automatic cron/dream cycle.

## Evidence model

M32 uses existing user messages as the evidence source. It does not create a
separate observation ledger.

For a current occurrence report such as:

- `Aku baru selesai lari pagi`
- `Aku habis lari pagi`
- `I just finished yoga`

M32 derives a normalized activity signature and checks recent user messages
across conversations.

A pattern qualifies only when all of these are true:

1. at least 4 matching occurrences;
2. at least 3 distinct calendar days;
3. evidence spans at least 7 days;
4. the current message itself is an occurrence of that activity;
5. the activity is not in a blocked sensitive/state class.

These thresholds are deliberately conservative.

## Explicit routine assertions

Messages such as:

- `Saya biasanya lari pagi setiap Senin`
- `Aku gym 3 kali seminggu`
- `I usually read before bed`

are explicit user-authored assertions. M32 does not reinterpret them as
inference. `background_extraction_gate` routes them into the existing
`memory_intelligence` path, which preserves normal provenance semantics.

## Inferred habit projection

A qualified M32 pattern is projected into the existing `memories` table:

- `category = routines`
- `kind = context`
- `source = auto`
- `source_priority = repeated_pattern`
- deterministic hashed `structured_field`
- bounded evidence snippets
- qualified content: `User appears to have a recurring routine involving: …`

No new schema is required.

M32 inferred confidence is capped at `0.54`, intentionally below
`memory_lifecycle_governance.LOW_CONFIDENCE_THRESHOLD = 0.55`.

Therefore M31F continues to treat an M32 habit as unverified personal context
until stronger user-authored evidence exists.

Repeated evidence can refresh an M32-owned inferred memory but does not set
`last_confirmed_at`, because repeated observation is not confirmation.

## Corrections

Explicit cessation messages such as:

- `Aku sudah tidak lari pagi lagi`
- `Saya berhenti lari pagi`
- `I no longer run`
- `I stopped yoga`

may supersede an exact matching M32 inferred habit.

The correction path is restricted to memories that are simultaneously:

- `source = auto`;
- `source_priority = repeated_pattern`;
- exact M32 deterministic `habit_pattern_*` field.

Manual or explicit-user routine memories are never superseded by M32.

## Sensitive inference gate

M32 refuses automatic habit inference for sensitive classes including:

- medical treatment;
- religion;
- politics;
- sexual activity;
- substance use.

It also excludes simple emotional/physical states so repeated statements such
as `tired` or `stressed` are not mislabeled as habits.

Explicit user-authored statements remain governed by the existing memory
system; M32 only constrains automatic pattern inference.

## CognitiveRuntime ownership

`chat.py` remains responsible for FastAPI background-task scheduling.

The cognitive operation itself is behind `CognitiveRuntime`:

```text
chat.py
  -> CognitiveRuntime.classify_habit_signal()
  -> CognitiveRuntime.learn_habits_from_chat()
  -> habit_learning
```

Existing services do not import `CognitiveRuntime`.

`COGNITIVE_RUNTIME_VERSION` remains `M31D-v1`.

## M31F interaction

For inferred occurrence learning:

```text
M31F allow_background_inference == true
    -> M32 occurrence learning may run
M31F allow_background_inference == false
    -> M32 occurrence inference is held
```

Explicit habit corrections are user-authored corrections rather than
background inference, so they may still supersede an exact M32-owned inferred
pattern.

Explicit routine assertions stay in `memory_intelligence`, whose M31F
projection posture already distinguishes explicit user evidence from inferred
`repeated_pattern` candidates.

## Observability

M32 returns a structured `HabitLearningAudit` with:

- version;
- signal type;
- action;
- hashed pattern ref;
- history row count;
- occurrence count;
- distinct day count;
- span;
- canonical reason codes.

Logs contain no raw activity, message, or evidence text.

Because habit learning runs after response generation as a background encoding
operation, M32 does not emit a second per-turn `CognitiveDecisionTrace`.
This preserves the one-final-trace invariant established by M31F/M31G.

## Failure model

History retrieval, embedding, or persistence failures are non-critical.

M32 fails open:

- the user response is already streamed;
- no guessed habit is written on failure;
- later qualifying occurrences can retry learning naturally;
- safe background execution remains the transport-level isolation boundary.

## Relationship to existing services

### `memory_intelligence.py`

Authoritative for explicit routine assertions and normal memory provenance.

### `memory_consolidation.py`

Existing manual-trigger deterministic consolidation remains unchanged. M32 is
habit-specific and does not turn consolidation into automatic recurring work.

### `goal_intelligence.py`

Habits may be relevant to a goal, but M32 never auto-creates a goal.

### `proactive_nudges.py`

A learned routine is not authorization to contact the user. M32 never creates
a nudge/reminder from inference.

## Definition of done

M32 is complete when:

- one occurrence cannot become a habit;
- multi-day / minimum-span evidence is required;
- inference is deterministic and LLM-free;
- inferred memories remain unverified under existing M31F governance;
- explicit routine assertions keep their existing provenance path;
- explicit correction can remove only M32-owned inference;
- sensitive habit inference is blocked;
- no new DB schema or infrastructure is introduced;
- no second cognitive trace is emitted;
- targeted M32/M31 regression tests pass;
- full backend regression passes;
- `git diff --check` is clean.

## Next milestone

M33 may formalize consolidation / dream-cycle behavior. M32 does not implement
that milestone.
