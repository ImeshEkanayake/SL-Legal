# V2 Phase 6 Operations Runbook

## Release Flow

1. Confirm the previous phase release, commit, and detached logs.
2. Run targeted tests for changed areas.
3. Run detached backend tests:

```bash
scripts/run_detached_quality_gate.sh tests phase6-tests
```

4. Run detached frontend quality:

```bash
scripts/run_detached_quality_gate.sh frontend phase6-frontend
```

5. Run the load scenario dry run:

```bash
scripts/run_detached_quality_gate.sh load-plan phase6-load-plan
```

6. On a production-like stack, run the real load suite:

```bash
SL_LEGAL_API_BASE_URL=http://127.0.0.1:8000 \
SL_LEGAL_LOAD_TEST_USER_ID=<user_id> \
SL_LEGAL_AUTH_HMAC_SECRET=<32+ char secret> \
SL_LEGAL_LOAD_TEST_CASE_ID=<case_id> \
SL_LEGAL_LOAD_TEST_PACK_ID=<pack_id> \
SL_LEGAL_LOAD_TEST_PACK_ITEM_ID=<pack_item_id> \
scripts/run_detached_quality_gate.sh load phase6-load
```

7. Run production health and benchmark gates:

```bash
PYTHONPATH=rag uv run --with 'psycopg[binary]' python scripts/check_rag_production_health.py
PYTHONPATH=rag uv run --with 'psycopg[binary]' python scripts/run_production_benchmark_gates.py
PYTHONPATH=rag uv run --with pydantic python scripts/run_v2_for_against_retrieval_eval.py
```

8. Run secret scan and staging checks before GitHub upload.

## Metrics Review

Check JSON metrics:

```bash
curl -H "X-SL-Legal-User-ID: <user>" \
  -H "X-SL-Legal-Auth-Timestamp: <timestamp>" \
  -H "X-SL-Legal-Auth-Signature: <signature>" \
  -H "X-SL-Legal-Body-SHA256: <sha256>" \
  http://127.0.0.1:8000/v1/operations/metrics
```

Check Prometheus metrics:

```bash
curl -H "Authorization: Bearer $SL_LEGAL_METRICS_BEARER_TOKEN" \
  http://127.0.0.1:8000/v1/operations/metrics/prometheus
```

Review:

- request count by route
- error count by route
- max and average request latency
- rate-limit rejections
- oversized body rejections
- audit-write failures

## Incident Response

For retrieval degradation:

1. Check API error and latency metrics.
2. Run `scripts/check_retrieval_services.py`.
3. Run `scripts/check_rag_index_consistency.py`.
4. Run `scripts/check_rag_production_health.py --allow-failures` to collect failures.
5. If OpenSearch or Qdrant is stale, rebuild from the clean Postgres export using `scripts/reload_external_indexes_from_clean_postgres_export.sh`.

For source viewer failures:

1. Check page anchors through `/v1/research/packs/{pack_id}/items/{pack_item_id}/source`.
2. Verify `pack_item_source_anchors` status.
3. Verify page text exists in `pages`.
4. If anchors are missing, run `scripts/backfill_source_anchors.py`.

For review workflow failures:

1. Confirm signed auth is valid.
2. Check `/v1/cases/{case_id}/review/items`.
3. Confirm the review target exists in `drafts` or `legal_claims`.
4. Inspect audit events for `review.decision.recorded`.

## Rollback

Code rollback:

1. Identify the last known-good GitHub release tag.
2. Deploy that tag.
3. Run backend and frontend quality gates.
4. Run smoke checks for workspace, source viewer, and review queue.

Database rollback:

- Phase 6 applies no database migration.
- If a future migration is involved, use a separately reviewed rollback plan before deployment.

Data/index rollback:

1. Keep raw data immutable.
2. Rebuild search indexes from Postgres exports rather than editing indexes manually.
3. Verify with `scripts/check_rag_index_consistency.py`.
4. Verify adverse retrieval with `scripts/run_v2_for_against_retrieval_eval.py`.

## Corpus Quality Audit

Run:

```bash
PYTHONPATH=rag uv run --with 'psycopg[binary]' python scripts/audit_full_corpus_searchability.py
PYTHONPATH=rag uv run --with 'psycopg[binary]' python scripts/check_rag_production_health.py
```

Review:

- documents without searchable pages
- chunks missing citation or metadata
- documents missing original assets
- text versions missing digests
- missing sources register
- OCR and translation quality flags

## Data Hydration

Use the object storage runbook for corpus assets:

```text
Docs/object_storage_asset_sync_runbook.md
```

After hydration:

1. Load pages.
2. Sync text versions.
3. Build RAG chunks.
4. Load Postgres chunks.
5. Load OpenSearch.
6. Load Qdrant.
7. Run health and benchmark gates.

## Release Evidence Checklist

Attach or reference:

- backend detached log
- frontend detached log
- load-plan or load-test log
- real load-test report for production deployment
- secret scan result
- marker scan result
- browser verification note when UI files changed or before production deployment
- GitHub commit, tag, and release URL
