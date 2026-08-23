# Memory Intelligence Status

Last updated: 2026-08-23

## Current status

Memory Intelligence MR0–MR7 is complete and production-verified.

## Shipped architecture

User message -> chat router calls memory.retrieve_relevant(...) -> retrieval gate blocks public/current or low-signal queries -> sparse personal query normalizer may append retrieval hints -> embeddings + match_memories RPC retrieve wider candidates -> Python reranking filters active memories and scores metadata -> memory context packer selects prompt-safe items under budget -> route-aware packing prioritizes identity/self-regulation when relevant -> conversation summaries are retrieved separately through episodic routing -> lifecycle telemetry logs aggregate active/hidden/stale/confirmation counts.

## Final backend health

566 passed, 0 failed.

## Accepted retrieval quality baseline

- measured recall@5 = 1.0000 on the local live eval set
- recall@10 >= 0.90
- MRR = 1.0000
- hit rate = 1.0000

## Accepted packed-context quality baseline

- packed hit rate = 1.0000
- packed MRR = 1.0000
- negative false positives = 0

## Production verification checklist

Verified in production logs:
- weather/public-current: summary retrieval gate returned=0; memory_context memories=0 summaries=0.
- identity: summary retrieval returned=1; memory retrieval returned=8; lifecycle trace emitted; packer intent=identity.
- self-regulation: memory retrieval returned=12; lifecycle trace emitted; packer intent=self_regulation.
- Aliyya backend: summary trace episode=dev_project; memory trace emitted.

No production evidence of memory retrieval rpc failed, summary retrieval rpc failed, 500, Traceback, or ERROR.

## Deferred work

1. Turn expected-empty probes into a stronger regression gate.
2. Refactor chat.py through pure moves before adding new chat features.
3. Add telemetry persistence only when dashboard/trend review is needed.
4. Revisit hybrid/RRF/HNSW/reranker only when eval evidence shows current stack is insufficient.

## Chat Runtime Hardening Closeout

Status: closed for current cycle.

- C1 public/current gate regression hardening is shipped and production-verified.
- D1 chat runtime refactor hardening is closed for this cycle:
  - memory assembly extracted into `app/services/chat_memory_assembly.py`;
  - calendar helper utilities extracted into `app/services/chat_calendar_helpers.py`;
  - runtime service wiring and stream/background wiring are protected by regression tests.
- E1 telemetry readback is audited and intentionally deferred:
  - retrieval, summary, lifecycle, packer, and chat memory-context telemetry remain log-based;
  - persistence/readback/dashboard should be added only when trend review or an operator dashboard is needed.

Guardrail: do not remove runtime service imports from `app/routers/chat.py` unless the corresponding stream/background callsites have been moved and covered by tests.

## B1 Retrieval Recall Evidence Closeout

Status: closed with measured local live-eval evidence.

Measured on local live eval set `backend/eval/retrieval_eval.local.json` using `tools/eval_retrieval.py --top-k 5 --diagnostics`.

Results:
- positive queries: 5
- recall@5: 1.0000
- recall@10: 1.0000
- MRR: 1.0000
- hit rate: 1.0000
- mean first-hit rank: 1.0000
- mean hit similarity: 0.9697

Threshold evidence:
- threshold 0.40: recall@5 1.0000, recall@10 1.0000, MRR 1.0000, hit rate 1.0000
- threshold 0.50: recall@5 0.4000, recall@10 0.4000, MRR 0.4000, hit rate 0.4000

Decision:
- Keep the personal-cue retrieval threshold behavior that enabled the measured recall recovery.
- Keep public/current negative probes gated out of production retrieval.
- Do not commit `backend/eval/retrieval_eval.local.json`; it remains local and gitignored.
