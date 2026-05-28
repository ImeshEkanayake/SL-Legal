# Phase 6 Hybrid Retrieval Review

**Phase:** 6 - Hybrid retrieval  
**Status:** Repo-owned implementation complete for exact/BM25/fuzzy/vector/fusion contracts; production approval pending benchmark and live index performance review.  
**Date:** 2026-05-24

## Scope

Phase 6 builds the retrieval layer that feeds Legal Research Packs. The LLM must
not reason directly from raw PDFs or hidden model memory; it receives only
retrieved, cited pack items.

## Implemented Controls

- Exact citation/provision resolver:
  - Act number and year signals
  - section/article/provision signals
  - case-name signals such as `Perera v Silva`
- OpenSearch payload builder:
  - BM25-style multi-match
  - phrase match
  - fuzzy match
  - filters for document type, source, authority, year range, and language
- Qdrant dense-vector retrieval path.
- Reciprocal Rank Fusion with exact-citation boost and legal authority boosts.
- Retrieval evidence is preserved per fused hit.
- Missing-source summary is produced when no fused candidates are found.
- Research pack creation records retriever counts and retrieval configuration.

## Test Evidence

Focused tests:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport pytest tests/test_exact_citation_resolver.py tests/test_hybrid_retrieval.py -q
```

Required final check:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport python scripts/run_quality_checks.py
```

## Review Findings

No repo-owned blocker remains for Phase 6 retrieval contracts.

Production approval still requires live corpus benchmark results, OpenSearch and
Qdrant index-performance review, sparse retrieval or equivalent learned sparse
path evaluation, and legal-domain review of known misses.

## Required External Signoffs

- Retrieval benchmark review.
- Index mapping/performance review.
- Lawyer/domain review of search results for golden questions.
- Infrastructure review of OpenSearch/Qdrant capacity.

## Gate Decision

Engineering gate: passed for Phase 6 hybrid retrieval contracts.  
Production approval gate: pending benchmark and performance signoff.
