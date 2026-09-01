# M31F — Deterministic Metacognitive Policy

**Status:** Implemented by the M31F major patch
**Scope:** M31F only. M31G salience and M32+ remain out of scope.

## Purpose

M31F adds a deterministic metacognitive policy layer between already-produced
cognitive state and response generation. The LLM still reasons and renders
language, while deterministic policy decides the epistemic posture of the turn.

Canonical response postures:

- `proceed` — available evidence is sufficient for normal generation.
- `caution` — generation may proceed, but uncertain personal evidence must not
  be presented as established fact.
- `clarify` — the runtime requires one concise clarification question before a
  substantive answer that depends on the unresolved point.

## Evidence trust

M31F does not create a global confidence score. It reuses existing memory
lifecycle governance and keeps separate concepts separate.

Evidence trust states:

- `not_applicable`
- `trusted`
- `mixed`
- `unverified`
- `unavailable`

Low-confidence and stale memory use the existing lifecycle governance
assessment. M31F does not redefine the low-confidence threshold.

## Durable projection

M31F introduces a deterministic durable-projection posture:

- `eligible`
- `hold_for_confirmation`

When projection is held, inferred memory candidates such as repeated-pattern
inference are blocked. Explicit user statements, direct answers in context, and
user corrections remain eligible subject to the existing Memory Intelligence
confidence/source gates.

This protects the Life Model and memory substrate from unresolved inference
without preventing the user from explicitly teaching or correcting Aliyya.

## Clarification signals

M31F is deliberately conservative. Clarification is triggered only by bounded,
inspectable signals such as:

- an unresolved short referent with no usable conversation history;
- contradictory selected structured memory values;
- repeated explicit rephrase/misunderstanding cues;
- required personal context whose retrieval failed or whose selected evidence
  is unverified.

A single rephrase cue produces `caution` rather than immediate clarification.

## Runtime integration

The runtime order is:

```text
context retrieval / packing
        ↓
WorkingMemoryState
        ↓
M31F deterministic policy
        ↓
CognitiveDecisionTrace finalization
        ↓
high-priority epistemic prompt directive (only if needed)
        ↓
LLM generation
        ↓
background persistence with M31F inference gate
```

`CognitiveRuntime` owns M31F sequencing. `chat.py` does not import the
metacognitive service directly.

## Trace

The existing one-trace-per-turn model is preserved. M31F trace metadata includes:

- response posture;
- evidence trust;
- durable projection posture;
- background-inference permission;
- pseudonymizable unverified memory refs;
- canonical M31F reason codes.

Trace emission remains fail-open and never blocks the user response.

## Failure semantics

If M31F policy evaluation itself fails unexpectedly, the runtime returns a
behavior-preserving safe default:

- `response_posture = proceed`
- `durable_projection_posture = eligible`
- `allow_background_inference = true`

The failure is logged without raw user or memory content. Trace failure also
remains fail-open.

Deterministic assistant-mode commands and authoritative Calendar receipts continue to short-circuit before model generation; their existing deterministic policy remains authoritative.

## Explicit exclusions

M31F does not:

- compute salience;
- add a salience score to memory or trace;
- replace relevance/ranking;
- add a new database or table;
- call an LLM from the policy service;
- create autonomous agents;
- implement habits, consolidation, or dream-cycle behavior;
- expose internal reason codes or memory identifiers to the end user.

M31G remains the next cognitive milestone.
