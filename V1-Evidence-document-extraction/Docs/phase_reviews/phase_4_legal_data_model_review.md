# Phase 4 Legal Data Model Review

**Phase:** 4 - Legal data model  
**Status:** Repo-owned schema contract complete, including object-storage asset tracking; production approval pending query-performance, backup/restore, and external architecture review.  
**Date:** 2026-05-26

## Scope

Phase 4 establishes the canonical database contracts for corpus data, cases,
legal units, retrieval chunks, citations, research packs, review workflow,
auditing, rate limits, operations rollups, ingestion traceability, file assets,
text versions, digests, and case-document relevance scores.

## Implemented Controls

- SQL migrations `001` through `011` are contiguous and documented.
- Core corpus tables:
  - documents
  - document versions
  - pages
  - file assets
  - document text versions
  - document digests
  - legal units
  - retrieval chunks
  - citations
  - missing sources
- Workspace/case tables:
  - organizations, users, projects, cases, permissions
  - case documents, raw inputs, facts, issues, evidence, timeline
- Agent/workflow tables:
  - chat threads/messages
  - agent runs/steps
  - tool calls
  - research packs/items
  - claims/citations
  - drafts/review items/tasks
- Operations and governance tables:
  - audit events
  - API rate limits
  - operational metric rollups
  - ingestion runs and document ingestion events
- Case relevance table:
  - case-document relevance scores with source, method, confidence, and review status
- Schema contract tests verify migration continuity, documentation coverage,
  required table coverage, and rollback-only smoke-test coverage.

## Test Evidence

Focused tests:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport --with boto3 pytest \
  tests/test_schema_contracts.py tests/test_db_access_layer.py tests/test_object_storage_sync.py -q
```

Required final check:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport --with boto3 python scripts/run_quality_checks.py --require-rag-indexes
```

## Review Findings

No repo-owned blocker remains for Phase 4 schema contracts.

Migration `011` adds the production object-storage layer without changing the
retrieval contract: the database stores metadata, searchable text, digests, and
relevance scores, while originals live in S3-compatible object storage. The RAG
health gate now distinguishes asset-only corpus records from searchable RAG
records: imported documents must retain their primary file asset, object key,
and original digest, while documents with page text must also retain text
versions, text assets, text digests, and retrieval chunks.

The loaded searchable layer now contains 1,927,382 page rows, 103,990
`current-pages-v1` document text versions, 1,573,476 retrieval chunks, and
matching Postgres/OpenSearch/Qdrant chunk counts. Documents without usable page
text are tracked as extraction/OCR/redownload backlog rather than silently
counted as searchable.

Production approval still requires workload-specific query plans, backup/restore
evidence, data-retention decisions, and review of indexes after real corpus and
case volumes are loaded.

## Required External Signoffs

- Database architecture review.
- Query performance review under expected corpus and case load.
- Backup/restore drill.
- Data retention and privacy review.

## Gate Decision

Engineering gate: passed for Phase 4 legal data model contracts.  
Production approval gate: pending performance and operations signoff.
