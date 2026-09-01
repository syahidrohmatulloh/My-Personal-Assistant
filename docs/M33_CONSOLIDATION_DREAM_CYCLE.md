# M33 — Consolidation / Dream Cycle

**Status:** Implemented by the M33 major patch
**Baseline:** M32 (`2b74152`)
**Version:** `M33-v1`

## Purpose

M33 formalizes deferred memory consolidation without turning the assistant into
a free-form autobiographical inference engine.

"Dream cycle" is an engineering metaphor for low-priority maintenance performed
outside the immediate chat turn. It is not generative dreaming.

## Canonical rule

> Consolidate evidence, not truth.

M33 may merge corroborating evidence into one existing trusted memory row. It
does not create a new semantic claim during the automatic cycle.

## Inputs

Only active durable memories with trusted user-authored provenance are eligible:

- `explicit_user_statement`
- `user_answer_in_context`
- `user_correction`
- explicit/manual user-owned memory sources

Existing lifecycle governance remains authoritative. Hidden or
`needs_confirmation` rows are excluded.

M32 inferred habits remain below the lifecycle confidence threshold and are
therefore not valid M33 source material until stronger user-authored evidence
exists.

## Pattern qualification

Two deterministic paths exist:

1. Structured repetition
   - same category
   - same structured field
   - same normalized structured value
   - at least two trusted source memories

2. Unstructured near-duplicate evidence
   - same category
   - no structured key
   - token-set similarity >= `0.82`
   - at least three trusted source memories

No embedding or LLM similarity decision is used.

## Persistence

M33 selects one existing trusted memory as the canonical target and merges up to
five unique evidence snippets into its existing `evidence` field.

The automatic cycle does **not** modify:

- content
- confidence
- source / source priority
- structured field/value
- `last_confirmed_at`
- lifecycle state
- archive/supersession state

It also does not insert a new memory row.

## Safety

The consolidation service excludes:

- identity synthesis
- important-date synthesis
- sensitive medical/religious/political/sexual/substance-use profiling
- hidden memories
- low-confidence or pending-review memory
- assistant-confirmation-only provenance
- repeated-pattern inference that has not become user-authored truth

M33 never creates reminders, goals, calendar events, or proactive nudges.

## Scheduler

`memory_consolidation_scheduler.py` provides the deferred cycle.

It is **disabled by default**.

Optional environment variables:

```text
MEMORY_CONSOLIDATION_SCHEDULER_ENABLED=true|false
MEMORY_CONSOLIDATION_INTERVAL_MINUTES=1440
MEMORY_CONSOLIDATION_INITIAL_DELAY_SECONDS=120
MEMORY_CONSOLIDATION_LOOKBACK_DAYS=30
```

The scheduler discovers users with recent memory activity, isolates failures per
user, runs deterministic consolidation, and keeps an in-process last-run status.

## CognitiveRuntime boundary

`CognitiveRuntime.consolidate_memories()` delegates to the authoritative M33
service for explicit orchestration use.

The scheduler itself remains an out-of-turn service and therefore does not
depend on `CognitiveRuntime`.

## Failure semantics

Source-load failure, target-load failure, and individual merge failure degrade
safely. They never block chat generation because M33 runs outside the foreground
response path.

## Non-goals

M33 does not:

- archive duplicates automatically;
- delete memory;
- synthesize personality claims;
- promote inferred habits to trusted truth;
- auto-run Haiku self-reflection;
- add new database infrastructure;
- change public HTTP request/response contracts.
