# M35c2a1 — Goal Reference Epistemic Preservation

## Status

Complete and frozen.

Verification:

- targeted regression: 20 passed;
- full backend regression: 1019 passed;
- production pre-commit deployment succeeded;
- Fly machines reached version 316 and `started`;
- no Supabase mutation;
- no historical memory repair.

The production write path now preserves provenance, confidence, and
confirmation state across goal-reference projection.

## Why this hotfix exists

M35c2c historical provenance audit exposed a surviving future-write leak.

The legacy memory writer correctly assigns provenance before goal-reference
normalization, but `convert_goal_duplicate_rows()` subsequently routes matching
rows through `convert_row_to_goal_reference()`.

Historically that function overwrote:

- `source_priority` with `explicit_user_statement`;
- `confidence` with a value that could rise to 0.90.

Therefore an assistant-originated plan could be:

1. correctly classified by M35c2a as `assistant_confirmation` at confidence
   0.54;
2. matched to an active Goals record;
3. incorrectly upgraded back to `explicit_user_statement` with high confidence.

## Canonical invariant

`Projection match != Evidence strength`

`Transformation != Provenance upgrade`

`Goal reference != Explicit user statement`

A transformation may change representation, category, or structured identity.
It must not silently strengthen the evidence that created the row.

## Policy

Goal-reference conversion may change:

- content;
- kind;
- category;
- structured_field;
- structured_value.

It must preserve existing:

- source_priority;
- confidence;
- last_confirmed_at.

If those epistemic fields are absent, conversion must not invent them.

## Non-goals

M35c2a1 does not:

- mutate historical memories;
- repair historical provenance;
- change Goals records;
- enable source-priority ranking;
- introduce a new provenance taxonomy value.

Historical repair resumes in M35c2c only after this future-write contract is
tested and deployed.
