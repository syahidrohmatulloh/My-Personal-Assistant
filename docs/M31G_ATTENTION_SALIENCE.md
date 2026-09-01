# M31G — Attention / Salience Model

**Status:** Implemented by the M31G major patch
**Baseline:** M31F commit `dcd1839`
**Scope:** deterministic intrinsic memory salience + attention overlay only

## Purpose

M31G gives Aliyya a deterministic attention layer after query-relevance
retrieval/packing has already selected memory context.

The canonical M31 ADR defines:

- **Fact confidence**: how reliable a stored assertion is.
- **Memory salience**: intrinsic importance of a memory to the user's life,
  independent of the current query.
- **Query relevance**: how related a candidate is to the current turn.
- **Policy certainty**: deterministic/heuristic policy applicability.

M31G keeps those axes separate.

## Core design

The runtime sequence becomes:

```text
retrieval / query relevance
        ↓
existing memory packer
        ↓
WorkingMemoryState
        ↓
M31F metacognitive trust / clarify policy
        ↓
M31G intrinsic salience
        ↓
attention eligibility
        ↓
single CognitiveDecisionTrace
        ↓
prompt directives
        ↓
Claude generation
```

M31G does **not** replace retrieval ranking and does **not** add salience into
the existing retrieval or packing score.

Only memories that were already selected by the existing relevance/packing
path are scored for canonical M31G salience.

## Intrinsic salience

`attention_salience.py` computes a bounded `0..1` score from query-independent
memory metadata:

- durable category prior;
- structured-field importance;

It deliberately does **not** use:

- current user query text;
- similarity;
- retrieval score;
- packing score;
- memory confidence;
- source priority;
- recency;
- the legacy optional retrieval `salience` field.

This keeps canonical salience independent of query relevance and epistemic
confidence.

## Deterministic category priors

The first M31G policy uses conservative intrinsic priors:

| Category | Base salience |
|---|---:|
| important_dates | 0.78 |
| constraints | 0.74 |
| identity | 0.66 |
| relationships | 0.66 |
| goals | 0.60 |
| projects | 0.54 |
| routines | 0.50 |
| preferences | 0.48 |
| context | 0.32 |
| unknown | 0.40 |

Core structured identity fields receive a bounded bonus. Other structured
fields receive a smaller bonus. The legacy optional `salience` field used by
`memory.py` retrieval ranking is intentionally **not** treated as canonical
M31G salience, so M31G does not relabel an older implementation score.

## Salience tiers

- `high`: `>= 0.70`
- `medium`: `>= 0.50` and `< 0.70`
- `low`: `< 0.50`

## Attention vs salience

Salience answers:

> How intrinsically important is this memory?

Attention answers:

> Of the already-relevant memories, which may receive extra emphasis now?

M31G therefore keeps a second deterministic step:

1. Score selected memory salience.
2. Exclude low-salience memories from extra emphasis.
3. Respect M31F epistemic policy:
   - unverified memories retain their salience score but can be suppressed from
     attention;
   - `clarify` posture suppresses memory emphasis for that response.
4. Emphasize at most two eligible memories.

Suppressing attention does not erase or rewrite the underlying salience score.

## WorkingMemoryState

M31G adds an additive `AttentionWorkingState` slice:

- `level`: `normal | elevated | high`
- `salient_memory_refs`
- `attended_memory_refs`
- `suppressed_memory_refs`

The M31C base builder still does not compute salience. M31G enriches the frozen
state through a deterministic `with_attention_state(...)` helper after
metacognitive and attention evaluation.

`MemoryWorkingState` still contains no `salience_score` or `packing_score`.

## Runtime ownership

`CognitiveRuntime.finalize_metacognitive_turn(...)` remains the single
post-working-memory finalization boundary for compatibility.

In M31G it now:

1. evaluates M31F metacognitive policy;
2. evaluates M31G attention/salience;
3. enriches `WorkingMemoryState` with attention refs/level;
4. renders M31F and M31G directives;
5. emits exactly one trace containing both decisions.

If M31G fails unexpectedly, it fails open to:

- attention level `normal`;
- no attended memory;
- no attention prompt directive;
- normal generation continues;
- trace emission is still attempted.

## Prompt behavior

The M31G directive is private model context and is emitted only when at least
one memory is eligible for attention.

It includes a bounded copy of at most two already-selected memory contents so
the model knows which selected context deserves proportionate emphasis.

The directive explicitly states that:

- salience is not confidence;
- salience is not query relevance;
- current explicit user statements win;
- M31F epistemic/clarification policy wins;
- internal refs/scores must not be exposed.

## Trace

M31G activates the previously reserved
`MemoryCandidateTrace.salience_score`.

Trace behavior:

- selected memory candidates may carry bounded `0..1` salience;
- unselected/unsupported candidates remain `None`;
- `AttentionTrace` records level and ref sets;
- candidate reason codes explain the intrinsic salience tier;
- logging pseudonymizes all `*_ref` and `*_refs` fields;
- raw memory content is never placed in the trace.

The trace version remains `M31B-v1`; later M31 phases add backward-compatible
fields to the existing trace envelope.

## Explicit exclusions

M31G does not:

- change memory retrieval thresholds;
- change embedding similarity;
- change `retrieval_score`;
- change `packing_score`;
- write salience into Supabase;
- introduce a salience database column;
- use an LLM to decide salience;
- compute salience from the current query;
- add habits/routine learning (M32);
- add consolidation/dream cycle behavior (M33);
- expose cognitive trace or salience scores to the user.

## Definition of done

M31G is complete when:

- canonical salience is query-independent;
- confidence/relevance/salience tests prove axis separation;
- attention respects M31F trust/clarify outcomes;
- `WorkingMemoryState` carries metadata-only attention state;
- trace salience is bounded and observable;
- chat accesses M31G only through `CognitiveRuntime`;
- policy failures fail open;
- targeted M31 tests pass;
- full backend regression passes;
- no frontend/API/DB migration is required.
