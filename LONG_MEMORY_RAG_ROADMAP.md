# Long Memory / RAG Roadmap — Actual Production Track

Last updated: 2026-08-23

## Executive summary

The original roadmap proposed chunking, hybrid lexical/vector retrieval, HNSW, reranking, multi-hop retrieval, and lifecycle hardening.

The shipped production track is different and pragmatic: eval harness, public/current query gate, personal near-miss recovery, query normalization, wider retrieval fan-in, budgeted prompt packing, route-aware packing, packed-context eval, episodic summary routing, runtime telemetry, and lifecycle governance telemetry.

This document is now the source of truth for shipped memory work.

## Actual shipped phases

| Phase | Status | What shipped | Key commits |
|---|---:|---|---|
| MR0 | DONE | Eval harness, local eval-set helper, threshold diagnostics, negative probes. | ec053e4, d4241ed, e394f9b, 5d50a47 |
| MR1 | DONE | Retrieval gate, personal near-miss threshold, query normalizer, retrieval trace logs. | 3b61f46, d6c872e, 24f327e, 17f87e0, 914484b |
| MR2 | DONE | Prompt memory context packer, wider retrieval fan-in, budgeted packing. | ecfd366, 63c1c87 |
| MR3 | DONE | Route-aware prompt packing for identity and self-regulation. | 85c8734, 85ad42a |
| MR4 | DONE | Packed-context eval harness and production observability. | 220f99f |
| MR5 | DONE | Episodic summary routing, summary gate, dynamic summary threshold, summary telemetry. | 5f4ed5e, 6cb0b6d, 32c9eb8 |
| MR6 | DONE | Runtime resilience, safe RPC failure behavior, elapsed telemetry. | fa6d936 |
| MR7 | DONE | Lifecycle governance telemetry for active, hidden, stale, and confirmation counts. | f6c4849 |
| Final QA | DONE | Backend suite clean and calendar/relationship compatibility repaired. | 509b1dd |

## Accepted evidence baseline

Retrieval quality:
- recall@5 >= 0.90
- recall@10 >= 0.90
- MRR = 1.0000
- hit rate = 1.0000

Packed-context quality:
- packed hit rate = 1.0000
- packed MRR = 1.0000
- negative false positives = 0

## Important interpretation

Global MIN_SIMILARITY remains strict. Personal-cue queries use a relaxed personal threshold so personal near-misses can be recovered without lowering the global floor. Public/current query handling is done through retrieval gating and expected-empty probes. Prompt packing remains budgeted and route-aware even when retrieval fan-in is wider.

## Deferred original roadmap items

| Item | Status | Reason deferred |
|---|---:|---|
| Memory chunk table | Deferred | Current memories are short and structured enough for direct retrieval. |
| Hybrid lexical/vector retrieval and RRF | Deferred | Gate, query hints, and personal relaxed threshold solved the immediate quality/safety issue. |
| HNSW migration | Deferred | Current corpus size does not justify index migration risk yet. |
| Cross-encoder / reranker | Deferred | Current packer and metadata scoring are sufficient for current eval quality. |
| Multi-hop graph retrieval | Deferred | No measured production need yet. |

## Current known gaps

P2 — Gate regression hardening: the gate intentionally defaults to allow ambiguous queries. Keep expanding expected-empty probes and promote repeated leaks into targeted tests.

P2 — Chat router size: backend/app/routers/chat.py is large and should be refactored through pure moves before the next major chat feature.

P3 — Telemetry readback: telemetry is currently log-based. Persist it only when trend review or dashboard readback is needed.
