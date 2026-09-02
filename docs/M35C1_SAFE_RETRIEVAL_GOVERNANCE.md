# M35c1 — Safe Retrieval Governance Contract Repair

## Status

Complete and frozen.

M35c1 passed targeted regression, full backend regression, production
Supabase migration verification, and a controlled post-migration retrieval
probe.

Final verification:

- targeted regression: 20 passed;
- full backend regression: 997 passed;
- RPC governance projection matched authoritative DB metadata;
- source_priority/status/archived/deleted_at projected for all sampled rows;
- last_confirmed_at remained intentionally absent;
- retrieved hidden memories: 0;
- packed hidden memories: 0;
- provenance ranking quarantine remained disabled;
- no historical memory backfill or rewrite.

## Baseline

M35a frozen baseline:

`4a97a5e3660cf996226f5f05ce48c4f104e5b61c`

M35b was read-only and produced no repository commit.

## Evidence from M35b

The production `match_memories` boundary loses lifecycle/provenance metadata.

Observed controlled probe:

- 12 memories retrieved.
- 5 memories packed.
- 1 retrieved memory was lifecycle-hidden in the authoritative DB.
- 0 hidden memories were packed in that sample.
- `source_priority`, `last_confirmed_at`, and `status` were absent from all
  12 RPC rows.
- 3 of 5 packed rows had inferential or ambiguous authoritative provenance.

This proves a retrieval-governance boundary defect. It does not prove that a
hidden memory reached the final prompt in the sampled run.

## Canonical invariant

Database lifecycle state must survive—or be enforced before—the retrieval
boundary.

A hidden memory must never depend on missing RPC metadata to remain hidden.

## M35c1 contract

The retrieval RPC must:

1. exclude `superseded = true`;
2. exclude `archived = true`;
3. exclude non-null `deleted_at`;
4. exclude lifecycle-hidden statuses;
5. project `source_priority`;
6. project `status`;
7. project `archived`;
8. project `deleted_at`;
9. retain existing retrieval fields and public Python contracts.

Python lifecycle filtering remains defense in depth.

## Confirmation-timestamp quarantine

`last_confirmed_at` is intentionally NOT projected in M35c1.

Historical rows contain confirmation timestamps created by older defaults and
writers that did not reliably distinguish user confirmation from inference.
Projecting that field now would activate contaminated confirmation timestamps
as ranking / recency / trust signals before historical repair.

Historical repair belongs to M35c2.

## Provenance-ranking quarantine

M35c1 projects `source_priority` so deterministic downstream governance can
inspect provenance.

However, historical provenance has not yet been repaired. Therefore merely
making `source_priority` visible must not give old rows a new positive ranking
or trust bonus.

`SOURCE_PRIORITY_RANKING_ENABLED` remains `False` through M35c1.

M35c2 may deliberately enable provenance ranking only after historical repair
evidence supports it.

## Non-goals

M35c1 does NOT:

- backfill memories;
- rewrite historical provenance;
- rewrite confirmation timestamps;
- delete memories;
- auto-confirm inferred memories;
- redesign memory review UI;
- change M31F, M32, M33, M34, or M35a epistemic invariants.

## Definition of Done

M35c1 is complete only when:

- targeted tests pass;
- full backend regression passes;
- migration applies successfully;
- RPC returns provenance/lifecycle metadata;
- RPC does not return hidden memories;
- `last_confirmed_at` remains absent from retrieval projection;
- `system_inference` remains lifecycle-unverified;
- repository ends clean in one milestone commit.
