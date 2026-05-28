# V2 Phase 7 Hosted Data Strategy

## Goal

Move toward production-hosted data without putting the corpus into normal Git.

## Storage Model

- GitHub stores V1/V2 code, contracts, manifests, tests, and small documentation.
- Object storage stores original PDFs, source files, extracted text assets, OCR text, and translation fallback assets.
- Postgres stores document records, object keys, digests, pages, text versions, retrieval chunks, packs, claims, drafts, review items, and audit trails.
- OpenSearch stores keyword and metadata retrieval indexes.
- Qdrant stores vector retrieval indexes.

## Upload Strategy

Do not upload corpus files directly to GitHub.

For production hosting:

1. Keep raw data immutable in object storage.
2. Record every object key and SHA-256 digest in Postgres.
3. Generate small manifests for each batch.
4. Sync in bounded batches with `scripts/sync_corpus_assets_to_object_storage.py`.
5. Rebuild pages, text versions, chunks, OpenSearch, and Qdrant from canonical records.
6. Run searchability audit, RAG health, index consistency, and benchmark gates.

## Batch Evidence

Every hosted-data batch should produce:

- object sync report
- text-version sync report
- chunk build report
- index load logs
- searchability audit JSON
- RAG health JSON
- index consistency JSON
- adverse retrieval evaluation output

Reports can be stored in object storage or release artifacts. Raw corpus files stay out of normal Git.

## Monitoring Cadence

Daily:

- RAG health
- Postgres/OpenSearch/Qdrant index consistency
- API metrics review
- failed ingestion or audit-write checks

Weekly:

- full searchability audit
- adverse retrieval evaluation
- production benchmark gate
- object storage inventory and digest sample

Before every production deployment:

- schema check
- rollback-only schema smoke
- RAG health with search indexes
- real signed load suite
- browser verification when UI changes are included

## Recovery

If hosted data is inconsistent:

1. Freeze new ingestion.
2. Export missing chunk IDs or document IDs.
3. Rebuild derived indexes from Postgres or canonical object storage.
4. Rerun health and consistency checks.
5. Attach reports to the incident or release record.

Derived search indexes can be rebuilt. Raw corpus objects and Postgres digests are the durable source of truth.
