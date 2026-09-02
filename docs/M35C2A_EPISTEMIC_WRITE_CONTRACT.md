# M35c2a — Stop-the-Bleeding Epistemic Write Contract

## Status

Complete and frozen.

M35c2a passed targeted regression, full backend regression, Supabase schema
migration verification, production deployment, and post-deployment corpus
verification.

Final verification:

- targeted regression: 38 passed;
- full backend regression: 1004 passed;
- `last_confirmed_at` database default is NULL;
- historical corpus remained 127 rows after migration and deployment;
- no historical row was rewritten by M35c2a;
- new automatic inserts explicitly write `last_confirmed_at = NULL`;
- repeated_pattern, assistant_confirmation, and system_inference cannot refresh
  an existing confirmation timestamp;
- only fresh direct user evidence may refresh confirmation;
- SOURCE_PRIORITY_RANKING_ENABLED remains False;
- historical confirmation cleanup is deferred to M35c2b.

Post-deployment historical baseline:

- total memories: 127;
- rows with historical confirmation timestamps: 127;
- historical repeated_pattern rows with timestamps: 10;
- system_inference rows with timestamps: 0;
- assistant_confirmation rows with timestamps: 0.

The repeated_pattern timestamp count is historical contamination and is not
interpreted as user confirmation.

## Baseline

M35c1 frozen commit:

`cf3c344e29042049660da7fc8c1b78762022d230`

## Why M35c2a comes before historical repair

M35b/M35c2 analysis found that historical `last_confirmed_at` cannot reliably
mean user confirmation.

Before repairing historical rows, every future writer must stop producing the
same ambiguity.

Historical mutation is therefore explicitly out of scope for M35c2a.

## Canonical invariant

`Insertion != Confirmation`

`Repetition != Confirmation`

`Inference != Confirmation`

`Assistant-originated plan != User statement`

A confirmation refresh requires fresh direct user evidence.

## Confirmation writers

May refresh an existing memory's `last_confirmed_at`:

- `explicit_user_statement`
- `user_answer_in_context`
- `user_correction`

Must not refresh it:

- `repeated_pattern`
- `assistant_confirmation`
- `system_inference`

## New rows

All new automatic memory rows explicitly write:

`last_confirmed_at = NULL`

The database also drops the historical `DEFAULT now()` so omitted fields cannot
silently synthesize confirmation.

## Legacy generic extraction

The generic writer extracts user facts/preferences/context and can also retain
assistant-authored plans.

User-origin facts/preferences/context remain:

- provenance: `explicit_user_statement`
- no synthetic confirmation timestamp

Assistant-originated plans become:

- provenance: `assistant_confirmation`
- confidence capped at `0.54`
- no synthetic confirmation timestamp
- lifecycle `needs_confirmation = true`

## Non-goals

M35c2a does not:

- change historical memory rows;
- null historical timestamps;
- rewrite historical provenance;
- enable `SOURCE_PRIORITY_RANKING_ENABLED`;
- alter M35c1 retrieval quarantine;
- add Memory Review UX.

Historical timestamp repair belongs to M35c2b.
Historical provenance repair belongs to M35c2c.
