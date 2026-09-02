# M35a — Epistemic Honesty Hotfix

Baseline: M34 `45bd417`.

Canonical invariant:

```text
USER SAID IT
!=
SYSTEM INFERRED IT
!=
PATTERN REPEATED
!=
USER CONFIRMED IT
```

## Scope

M35a fixes only two proven automatic inference writers:
`relationship_memory` and `mood_memory_feedback`.

It also introduces canonical `system_inference` provenance in
`memory_intelligence.py`.

## Policy

- `system_inference` is assigned by deterministic system code.
- The extraction LLM is not allowed to self-assign this provenance.
- Maximum system-inference confidence is `0.54`.
- Existing lifecycle trust threshold remains `0.55`.
- Therefore a fresh system inference immediately requires confirmation.
- Inferred writers explicitly persist `last_confirmed_at = NULL`.
- Re-observation may retain/raise evidence confidence only within the cap,
  but must not create a user-confirmation timestamp.

## Mood-memory nuance

The current `mood_memory_feedback` implementation evaluates the current turn
and current mood/task context. It does not establish cross-turn repetition
before producing the candidate. Therefore `repeated_pattern` is not an honest
provenance label for this writer in its current implementation.

## Database compatibility

The original memory schema restricts `source_priority` to five values.
M35a therefore includes a small CHECK-constraint migration adding
`system_inference`.

The original `last_confirmed_at` column also has `default now()`. M35a leaves
that global default intact for backward compatibility. The two inferred writers
explicitly write SQL NULL instead.

## Non-goals

- no historical memory backfill;
- no Memory Review UX changes;
- no global writer retrofit;
- no lifecycle-governance rewrite;
- no M31F rewrite;
- no M32/M33 behavioral expansion.
