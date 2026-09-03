# M35c2c — Historical Provenance Governance & Repair

## Status

Complete and frozen.

Verification:

- initial M35c2c full backend regression: 1031 passed;
- final targeted governance regression after PostgreSQL REAL-boundary correction: 35 passed;
- guarded Phase423 production migration: successful;
- historical corpus: 127 rows;
- `legacy_unknown`: 82;
- `system_inference`: 1;
- `explicit_user_statement`: 29;
- `repeated_pattern`: 10;
- `user_answer_in_context`: 3;
- `user_correction`: 2;
- historical NULL provenance remaining: 0;
- active `legacy_unknown`: 38;
- active `system_inference`: 1;
- deterministic system inference confidence capped: 1;
- historical confirmation NULL/preserved distribution remains 106/21;
- no content, evidence, structured value, lifecycle state, archive state,
  supersession state, or deletion state was rewritten by Phase423.

M35c2c establishes provenance as an operational governance signal while
preserving uncertain historical evidence instead of guessing its origin.

## Baseline

M35c2a1 frozen commit:

`443da41108c9a709656b449cc07283f591bceab6`

## Purpose

M35c2c repairs the historical provenance layer as one coherent
governance milestone.

It does not attempt to reconstruct evidence that no longer exists.

## Canonical invariants

`Unknown provenance != Explicit user statement`

`Projection match != Evidence strength`

`Inference != Truth`

`Insertion != Confirmation`

`Absence of evidence is not evidence of falsehood`

## Frozen historical corpus

`created_at < 2026-09-02 17:40:14+00`

Audited rows: 127.

Final classification:

- 82 `legacy_unknown`;
- 1 `system_inference`;
- 29 `explicit_user_statement`;
- 10 `repeated_pattern`;
- 3 `user_answer_in_context`;
- 2 `user_correction`.

`legacy_unknown` consists of:

- 42 rows whose historical provenance was NULL;
- 40 historical rows labelled explicit but whose `kind=plan`
  cannot safely distinguish user intent from assistant-originated plan
  or old projection behavior.

The single deterministically recoverable historical inference is the
known rule-writer fingerprint `ui_design_taste`.

## Storage vs writer taxonomy

`legacy_unknown` is a storage/audit provenance only.

New LLM extraction and deterministic writers must never create it.
New writers continue using the canonical current-write taxonomy.

## Runtime governance

M35c2c makes provenance operational:

- `legacy_unknown`, `system_inference`, and `assistant_confirmation`
  require confirmation unless a real confirmation timestamp exists;
- automatic rows with missing provenance are also treated as unverified;
- effective ranking confidence for unverified provenance is capped at
  0.54;
- prompt metadata marks unverified retrieved memory without exposing
  internal provenance labels;
- source-priority ranking is re-enabled only after historical repair.

## Historical mutation scope

Phase423 may mutate only:

- `source_priority`;
- `confidence`, and only for the one deterministic system inference.

It does not modify:

- content;
- evidence;
- structured field/value;
- confirmation timestamps;
- status;
- archive state;
- supersession state;
- deletion state.

## Deployment sequencing

1. patch + targeted/full local tests;
2. apply guarded Phase423 migration;
3. verify production historical distribution;
4. commit and push once;
5. deploy the committed runtime once.

This prevents source-priority ranking from becoming active before the
historical database has been quarantined.

## Next milestone

M35c3 — Memory Review Provenance UX.
