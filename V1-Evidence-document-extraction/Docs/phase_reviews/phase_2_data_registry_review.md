# Phase 2 Data Registry Review

**Phase:** 2 - Data registry  
**Status:** Repo-owned implementation complete for manifest validation, DB import, and object-storage asset sync; corpus sampling and ownership signoff required before production approval.  
**Date:** 2026-05-26

## Scope

Phase 2 turns the corpus CSV manifests into enforceable registry inputs for the
database-backed product.

## Implemented Controls

- Registry validation module: `rag/sl_legal_rag/data_registry.py`
- Manifest validation:
  - required document fields
  - duplicate `document_id` detection
  - downloaded/missing status counting
  - next-action requirement for missing document rows
- Missing-source normalization:
  - external missing ID
  - category
  - expected and known coverage
  - importance, risk, owner, status, last checked, notes
- Database migration: `rag/sql/009_missing_source_registry.sql`
  - extends `missing_sources` for registry-grade tracking
  - adds unique external missing-source IDs
- Import script: `scripts/import_data_registry.py`
  - validates manifest before writing
  - creates an `ingestion_runs` record
  - records per-document registry import events
  - upserts missing-source register rows
- Object-storage sync script: `scripts/sync_corpus_assets_to_object_storage.py`
  - supports dry-run and execute modes
  - copies originals into S3-compatible storage
  - records deterministic object keys, SHA-256 hashes, byte sizes, and object URIs
  - backfills current Postgres documents first and can later scale to the full manifest
  - optionally writes extracted-text assets and text-version rows from current page text
- DB access layer supports idempotent missing-source upserts.

## Test Evidence

Focused tests:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport --with boto3 pytest \
  tests/test_data_registry.py tests/test_db_access_layer.py tests/test_object_storage_sync.py -q
```

Required final check:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport --with boto3 python scripts/run_quality_checks.py --require-rag-indexes
```

## Review Findings

No repo-owned blocker remains for the Phase 2 data registry implementation.

The import path makes registry state durable, but production approval still
requires corpus owner review of category mapping, missing-source priorities, and
sampled file-tree accuracy.

Object-storage backfill completed for the original 103 searchable Postgres
documents, then the full downloaded manifest path copied all available originals
from `data/raw` into MinIO. Current asset-layer totals are 113,359 original
assets, 103,997 extracted-text assets, and 217,356 digests. The full manifest run
processed 113,358 downloaded records with 113,156 newly synced, 202 skipped as
already present, and 0 errors. The sync path remains resumable with
`--skip-existing-assets`, `--max-to-sync`, JSONL reports, batch commits, and
ingestion-run traceability for future incremental corpus updates.

The searchability audit path is now explicit:
`scripts/audit_full_corpus_searchability.py` writes JSON and CSV tracking under
`data/tracking/rag_searchability/`. The latest audit shows 103,990 fully
searchable documents, 7,601 documents needing page extraction, PDF repair,
redownload, or unsupported-format handling, and 1,768 documents needing OCR/text
recovery.

## Required External Signoffs

- Corpus owner review of source categories and missing-source priority.
- Legal/domain review of criticality labels for missing authorities.
- Sampling review against actual local files and downloaded source URLs.
- Licensing review for licensed or restricted source rows.

## Gate Decision

Engineering gate: passed for Phase 2 registry contracts and import path.  
Production approval gate: pending corpus/legal/licensing review.
