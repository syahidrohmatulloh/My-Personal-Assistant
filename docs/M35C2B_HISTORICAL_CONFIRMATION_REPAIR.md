# M35c2b — Historical Confirmation Repair

## Status

Complete and frozen.

M35c2b passed local targeted regression, full backend regression, final
production preflight, guarded Phase 422 execution, and post-migration
verification.

Final verification:

- targeted regression: 32 passed;
- full backend regression: 1014 passed;
- historical corpus: 127 rows;
- deterministic repair candidates: 106 rows;
- Phase414 migration fingerprint repaired: 37 rows;
- insert-time default signature repaired: 69 rows;
- historical `last_confirmed_at = NULL`: 106 rows;
- ambiguous timestamps preserved: 21 rows;
- active repaired rows now unconfirmed: 48 rows;
- repaired active rows below confidence 0.55: 0;
- ambiguous repeated_pattern timestamps preserved: 5 rows.

M35c2b changed only historical confirmation metadata. It did not establish,
remove, or alter memory truth.

## Baseline

M35c2a frozen commit:

`8e291619ddae410c34eb18af09d9fe9300dabded`

## Evidence

Read-only historical classification found:

- Phase414 migration fingerprint: 37 rows.
- Insert-time default signature: 69 rows.
- Deterministic repair candidates: 106 rows.
- Active repair candidates: 48 rows.
- Ambiguous timestamps preserved: 21 rows.
- Candidates that would become stale after repair: 0.
- Candidates below confidence 0.55 after repair: 0.

## Canonical rule

A historical timestamp is removed only when we can deterministically explain
how it was synthesized.

Absence of evidence is not evidence of falsehood.

Therefore M35c2b repairs confirmation metadata, not memory truth.

## Repair scope

The migration changes exactly:

`last_confirmed_at -> NULL`

for the frozen deterministic candidate set.

It does not modify:

- content;
- evidence;
- provenance;
- confidence;
- lifecycle state;
- structured values.

## Frozen corpus boundary

Only memories created before:

`2026-09-02 17:40:14+00`

are eligible.

This is the production rollout boundary for M35c2a.

Future memories and future genuine confirmations are outside the historical
repair domain.

## Deterministic classes

### B — Phase414 migration fingerprint

`last_confirmed_at` falls within:

`2026-05-18 07:11:00+00 <= timestamp < 2026-05-18 07:12:00+00`

Audited count: 37.

### C — insert-time default

Absolute difference between `last_confirmed_at` and `created_at` is at most
five seconds.

Audited C-only count after B precedence: 69.

## Ambiguous preservation

21 historical rows do not satisfy either deterministic signature.

M35c2b leaves them unchanged.

No heuristic repair is permitted.

## Fail-closed migration

Phase 422:

1. locks concurrent memory writes briefly;
2. materializes exact candidate IDs;
3. requires historical total = 127;
4. requires B = 37;
5. requires C = 69;
6. requires candidates = 106;
7. requires ambiguous = 21;
8. requires historical NULL timestamps = 0 before repair;
9. updates only materialized candidate IDs;
10. requires exactly 106 rows updated;
11. requires 106 historical NULL timestamps afterward;
12. requires exactly 21 historical timestamps remain.

Any mismatch aborts and rolls the transaction back.

## Non-goals

M35c2b does not:

- repair historical provenance;
- enable provenance ranking;
- decide whether a memory is true;
- delete or archive memories;
- touch the 21 ambiguous timestamps;
- change future write behavior.

Historical provenance repair belongs to M35c2c.
