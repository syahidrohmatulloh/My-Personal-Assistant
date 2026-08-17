# LONG_MEMORY_RAG_ROADMAP.md — Retrieval & Long-Term Context


---

## MR0 implementation notes — Retrieval Eval Harness

Status: REVIEW

Runtime impact: none. MR0 adds tooling only.

Files:
- `backend/app/services/retrieval_eval.py`
- `backend/tools/eval_retrieval.py`
- `backend/eval/sample_eval_set.json`
- `backend/tests/test_retrieval_eval.py`

Private eval sets must use `backend/eval/retrieval_eval.local.json`.
That file is gitignored and should contain real query labels by memory ID only,
not raw private memory content.

Run from `backend`:
- `uv run python tools/eval_retrieval.py`
- `uv run python tools/eval_retrieval.py --eval-set eval/retrieval_eval.local.json`

Baseline metrics to record after creating the private eval set:
- recall@5:
- recall@10:
- MRR:
- hit rate:
- mean first-hit rank:
- mean hit similarity:

Decision rule:
- relevant memory is retrieved but prompt feels crowded -> prioritize MR4 context packer.
- relevant memory is missed because memory is too long/multi-fact -> prioritize MR1 chunking.
- exact names/places are missed -> prioritize MR2 hybrid retrieval.

