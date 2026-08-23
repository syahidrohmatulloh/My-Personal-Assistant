# Memory Obsidian Projection Status

## Status

As of M8, the memory system has a read-only Obsidian-like projection stack built and tested locally.

This stack does not change runtime retrieval, does not write to the database, does not add migrations, and does not require deployment.

## Completed slices

| Slice | Status | Output | Runtime impact |
| --- | --- | --- | --- |
| M0b-v2 | Done | Live memory shape audit | None |
| M1-v2 | Done | Taxonomy readiness audit | None |
| M2 | Done | `memory_note_projection.py` pure service | None |
| M3 | Done | Local redacted note projection report | None |
| M4 | Done | `memory_note_index.py` pure index service | None |
| M5 | Done | Local redacted note index report | None |
| M6 | Done | `memory_graph_view_model.py` pure UI-ready view model | None |
| M7 | Done | Local redacted graph view report | None |

## Evidence from local audits

- M0b-v2 showed the live `memories` table has 124 fetched rows, one user, corrected p50 memory length of 12 words, p90 of 19 words, and 96.77 percent of rows below 50 words.
- M1-v2 showed taxonomy readiness across events, facts, preferences, identity, routines, goals, relationships, and constraints.
- M1-v2 showed entity projection signal from structured fields, timeline projection possibility, evidence projection possibility, and no recommended runtime retrieval change.
- M3, M5, and M7 generate redacted local reports only.

## Current architecture

Existing runtime retrieval remains unchanged.

New read-only projection path:

```text
memories rows
  -> memory_note_projection.project_memory_rows
  -> memory_note_index.build_note_index
  -> memory_graph_view_model.build_memory_graph_view_model
  -> local redacted eval reports
```

## Safety boundaries

- No runtime retrieval change has been made.
- No database write path has been added.
- No schema migration has been added.
- No frontend exposure has been added.
- No Memory Safety PIN behavior has been weakened.
- No public-current retrieval gate behavior has been changed.
- No calendar review-first behavior has been changed.
- Local eval outputs under `backend/eval/*.local.json` must remain untracked.

## M8 decision

Decision: close out the read-only projection foundation with documentation before adding endpoint or UI exposure.

Recommended next path:

1. M8 docs closeout.
2. M9 PIN-gated read-only backend endpoint for graph view model.
3. M10 backend endpoint tests and auth safety guards.
4. M11 frontend review UI prototype only after endpoint is stable.

## Not recommended yet

- Do not add graph tables yet.
- Do not alter vector retrieval yet.
- Do not use graph expansion in chat retrieval yet.
- Do not expose raw source conversation IDs in frontend.
- Do not expose raw evidence trails without PIN-gated review design.

## Future endpoint design notes

A future endpoint should be read-only and PIN-gated if it exposes personal memory browsing.

Candidate path:

```text
GET /memory/graph-view
```

Expected behavior:

- Auth required.
- Memory Safety PIN required or equivalent existing memory-review gate.
- Return projected note cards, tag sections, entity sections, timeline sections, and candidate backlinks.
- Do not return raw source conversation IDs.
- Do not mutate memory rows.
- Do not affect chat retrieval.

## Deployment note

M2 through M8 do not require deployment unless a future endpoint or runtime consumer imports the graph view model.

## Live rollout closeout

Status: live in production.

Completed rollout:
- Backend endpoint: `POST /memory-review/graph-view`.
- Frontend UI: read-only `Graph View` tab inside `/memories`.
- Access control: Memory Safety PIN required before loading graph data.
- Auth path: browser session -> Next.js `/api/memory-review/...` proxy -> backend Bearer token.
- Runtime behavior: read-only projection only.
- Retrieval behavior: unchanged.
- Database schema: unchanged.
- Memory writes: none from graph view.
- Frontend runtime: Node engine updated to `24.x`.

Production smoke coverage:
- Positive graph-view load with correct Memory PIN.
- Negative graph-view load with wrong PIN rejected.
- Local UI smoke passed.
- Production frontend deploy completed and aliased to the live app.

Known boundary:
- This is not yet a full editable Obsidian graph.
- Tags, entities, timeline anchors, and candidate backlinks are projected from existing memories.
- Future phases may add search, filtering, manual note linking, or graph visualization after separate audit and tests.
