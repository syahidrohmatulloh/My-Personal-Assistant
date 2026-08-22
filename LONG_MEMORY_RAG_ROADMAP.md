# LONG_MEMORY_RAG_ROADMAP.md — Retrieval & Long-Term Context

A phased plan to grow Aliyya from good single-vector retrieval into durable
long-term memory that stays accurate, cheap, and calm. Grounded in the code
(Voyage embeddings, Supabase/Postgres pgvector, `match_memories` RPC,
`memory.retrieve_relevant` Ranking 2.0, conversation summary). One phase = one
small, reviewable, hash-guarded patch. **Upgrade, not rebuild** — every phase
extends the existing `retrieve_relevant` / `match_memories` seam; never a
parallel retriever.

---

## Baseline — what already exists (audited)

- **Embeddings:** Voyage `voyage-3.5-lite`, 1024-dim, correct `input_type`
  split (document vs query).
- **Store + index:** `memories.embedding vector(1024)`, `ivfflat`
  `vector_cosine_ops`, retrieval via `match_memories` (`<=>` cosine).
- **Retrieval:** `retrieve_relevant(user_id, query, limit)` — user-scoped
  top-k, `MIN_SIMILARITY` filter, dedup gate.
- **Ranking 2.0:** blends similarity + recency + confidence + salience +
  source/metadata priority; excludes archived/superseded.
- **Working context:** `trim_history` (char budget), `conversation_summary`
  (every 10 msgs / on idle).

## The real gaps (what limits "long" memory today)

1. Whole-memory embedding, no chunking -> one vector per blob hurts precision.
2. `ivfflat` recall ceiling as vectors grow (`hnsw` is better at scale).
3. Vector-only retrieval -> exact tokens (names/places/rare terms) can be missed.
4. Fixed `limit`, no budget-aware packing/diversification.
5. Single-hop only (no query expansion).
6. History trimmed to a stub, not summarized into durable episodic memory.
7. No retrieval evaluation harness (addressed by MR0).

---

## Phase table (at-a-glance)

| Phase | Name | Type | Risk | Status |
|------|------|------|------|--------|
| MR-1 | Intent-routing safety (self-regulation guard) | hotfix | low | DONE |
| MR0 | Retrieval eval harness | tooling | low | DONE |
| MR0.1 | Private eval-set helper + baseline capture | tooling | low | REVIEW |
| MR1 | Memory chunking + granular embeddings | schema+pipeline | med | TODO |
| MR2 | Hybrid retrieval (vector + lexical) | retrieval | med | TODO |
| MR3 | `hnsw` index migration | schema | low | TODO |
| MR4 | Budget-aware context packer | assembly | med | TODO |
| MR5 | Rolling episodic memory | pipeline | med | TODO |
| MR6 | Multi-hop / query expansion | retrieval | high | TODO |
| MR7 | Reranker pass (optional) | retrieval | med | TODO |

**Ordering:** measure before tuning. MR-1 (routing) and MR0/MR0.1 (measure)
come first. Then the MR0.1 baseline decides MR1 vs MR4:
- relevant memory **found but prompt crowded** -> MR4 (context packer) first.
- relevant memory **missed because memories are long** -> MR1 (chunking) first.
MR2 (exact terms), MR3 (scale), MR5 (long conversations), MR6/MR7 (reach) follow
as the numbers justify.

---

## MR-1 — Intent-routing safety (DONE)

Self-regulation preferences ("kalau aku overthinking, ingetin aku...") route to
memory, not calendar; concrete date/time reminders still route to Calendar.
Guard: `looks_like_self_regulation_memory_preference` (broadened emotion
vocabulary; concrete-time exclusion preserved).

## MR0 — Retrieval eval harness (DONE)

Offline harness over the existing `retrieve_relevant` path computing recall@5,
recall@10, MRR, mean first-hit rank, mean hit similarity, hit rate. Judged by
memory ID only; private sets gitignored; synthetic sample committed. See the
implementation notes at the bottom of this file.

## MR0.1 — Private eval-set helper + baseline capture (REVIEW)

**Why:** MR0 scores an eval set but nothing helps you *build* one — hand-copying
UUIDs out of Supabase is the friction that stops a baseline from ever being
captured, and without a baseline MR1/MR4 can't be chosen by numbers.

**Scope (tooling only, read-only):** `tools/build_eval_set.py` reuses
`get_supabase()`, runs the real `retrieve_relevant` to preview candidate
memories (redacted content shown **in the terminal only**), and records your
chosen relevant IDs into `eval/retrieval_eval.local.json` (gitignored,
IDs/notes only — never content).

**Done when**
- [x] `--query` previews candidates (redacted) with IDs + scores.
- [x] `--relevant-ids` records an IDs-only labeled query to the local file.
- [x] `--dry-run` shows without writing; `--output`/`--limit`/`--notes` work.
- [x] Helper logic unit-tested without Supabase.
- [ ] **You:** build ~30-50 queries, run the MR0 harness, fill the baseline.

**Baseline (fill me in after MR0.1):**

| metric | value | date |
|--------|-------|------|
| recall@5 | _tbd_ | |
| recall@10 | _tbd_ | |
| MRR | _tbd_ | |
| mean first-hit rank | _tbd_ | |

**Rollback:** delete `tools/build_eval_set.py` + its test; no runtime touched.

## MR1 — Memory chunking + granular embeddings (TODO)

One vector per fact, not per blob. Child `memory_chunks` table + conservative
splitter; search chunks, group to parent; legacy whole-memory embeddings stay
valid; lazy backfill. Gate: MR0 recall@5 improves vs baseline.

## MR2 — Hybrid retrieval (vector + lexical) (TODO)

Add a lexical arm (Postgres `tsvector`/trigram) fused with vector scores (RRF)
so exact names/places/rare terms aren't missed. One retrieval path, fusion
weight tunable (->0 = vector-only rollback).

## MR3 — `hnsw` index migration (TODO)

Add `hnsw (vector_cosine_ops)` (verify pgvector >= 0.5); keep `ivfflat` until
proven, then drop. No app code change (same `<=>`). Scale/latency phase.

## MR4 — Budget-aware context packer (TODO)

Between retrieval and prompt: token-budget-aware selection, near-duplicate drop,
light MMR diversification. Ranking 2.0 stays the scorer; packer is the selector.
Rollback: pass-through top-k.

## MR5 — Rolling episodic memory (TODO)

Layered `conversation_summary` (running episodic note + extracted durable facts
into the memory pipeline, deduped); inject on trim instead of a bare stub.
Keeps long conversations coherent without context bloat.

## MR6 — Multi-hop / query expansion (TODO)

Cheap Haiku expansion -> 1-2 sub-queries on detected multi-part intent; union +
re-rank; hard hop/cost cap. Gated, not per-turn.

## MR7 — Reranker pass (optional) (TODO)

Cross-encoder / Voyage reranker on the top ~30 -> final set, only if MR0 shows
MR1-MR4 left precision on the table. Cost/latency budgeted.

---


## MR0.2 — Retrieval diagnostics + threshold sweep (REVIEW)

**Why:** the first MR0.1 baseline showed recall@5/10 = 0.4000 on a small
self-regulation eval set. The relevant memory existed and was active, and when
retrieval hit, it ranked #1. The likely miss mechanism is below-threshold
near-misses being hidden by production's `MIN_SIMILARITY = 0.5` gate.

**Scope:** tooling-only diagnostics. `memory.py`, `retrieve_relevant`, and
production `MIN_SIMILARITY` are not changed.

**Adds**
- per-query diagnostics in `tools/eval_retrieval.py --diagnostics`
- unfiltered read-only candidate fetch through the existing `match_memories` RPC
- dropped relevant IDs + similarity/retrieval_score
- read-only threshold sweep across 0.30, 0.35, 0.40, 0.45, 0.50
- pure tests in `tests/test_retrieval_eval.py`

**Run**

    cd backend
    uv run python tools/eval_retrieval.py --eval-set eval/retrieval_eval.local.json
    uv run python tools/eval_retrieval.py --eval-set eval/retrieval_eval.local.json --diagnostics

**Decision rule**
- if a slightly lower threshold recovers relevant IDs without many suspicious
  false positives, consider a small threshold tune as a measured runtime patch.
- if exact terms still miss after threshold visibility, evaluate MR2-lite hybrid
  or query normalization.
- do not start MR1 chunking unless MR0 shows misses caused by long/multi-fact
  memories rather than threshold filtering.

## Guardrails (carried from project doctrine)

1. Supabase/pgvector stays the source of truth (no Obsidian/flat-file core).
2. One retrieval path in app code — extend `retrieve_relevant` /
   `match_memories`, never a parallel retriever.
3. Voyage stays the embedder unless MR0 shows a real reason (dim change = full
   re-embed, its own project).
4. Measured, not asserted — MR0/MR0.1 gate the rest; each phase reports a delta.
5. Extra model calls (MR6/MR7) gated on intent, not per-turn.
6. Small pushes, hash-guarded idempotent patchers, tests/build before commit,
   one-line rollback per phase.

## Relationship to other tracks

- **v0.9 Memory Intelligence** = *what* is stored/scored; this roadmap = *how*
  it's retrieved and packed. They compose.
- **Home OS** cards read the same memory layer -> better retrieval improves the
  home for free.

---

## MR0 implementation notes — Retrieval Eval Harness

Status: DONE (landed as `ec053e4`).

Runtime impact: none. MR0 adds tooling only.

Files:
- `backend/app/services/retrieval_eval.py`
- `backend/tools/eval_retrieval.py`
- `backend/eval/sample_eval_set.json`
- `backend/tests/test_retrieval_eval.py`

Private eval sets must use `backend/eval/retrieval_eval.local.json`.
That file is gitignored and should contain real query labels by memory ID only,
not raw private memory content.

Build a private set with the MR0.1 helper:

    cd backend
    uv run python tools/build_eval_set.py --user-id <uuid> --query "..." --limit 10
    uv run python tools/build_eval_set.py --user-id <uuid> --query "..." --relevant-ids <id1>,<id2>
    uv run python tools/eval_retrieval.py --eval-set eval/retrieval_eval.local.json
