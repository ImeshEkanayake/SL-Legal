# Phase 7 Reranking and Evaluation Review

**Phase:** 7 - Reranking and evaluation  
**Status:** Repo-owned metric implementation complete; production approval pending golden legal benchmark results and reranker performance review.  
**Date:** 2026-05-24

## Scope

Phase 7 gives retrieval changes a measurable quality gate before they can feed
strategy or drafting features.

## Implemented Controls

- Retrieval evaluation module: `rag/sl_legal_rag/retrieval_eval.py`
- Deterministic metrics:
  - Recall@k
  - reciprocal rank
  - MRR
  - nDCG@k
  - missing-query ID reporting
- Minimum-bar helper for retrieval evaluation result objects.
- Existing legal-quality reranking remains in `rag/sl_legal_rag/retrieval.py`
  with authority and source-quality multipliers.

## Test Evidence

Focused tests:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport pytest tests/test_retrieval_eval.py tests/test_hybrid_retrieval.py -q
```

Required final check:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport python scripts/run_quality_checks.py
```

## Review Findings

No repo-owned blocker remains for Phase 7 metric contracts.

Production approval still requires a curated Sri Lankan legal retrieval
benchmark, measured Recall@20/MRR/nDCG results, and proof that any reranker
improves or preserves baseline retrieval quality.

## Required External Signoffs

- Golden legal question set review by lawyer/domain expert.
- Retrieval benchmark review.
- Reranker model selection review.
- Performance review for reranking latency and cost.

## Gate Decision

Engineering gate: passed for Phase 7 evaluation metric contracts.  
Production approval gate: pending golden benchmark and reranker review.
