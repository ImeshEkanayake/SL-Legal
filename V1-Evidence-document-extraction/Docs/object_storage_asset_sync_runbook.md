# Object Storage Asset Sync Runbook

## Purpose

This runbook moves downloaded corpus originals from `data/raw` into the local
S3-compatible MinIO store and records durable asset metadata in Postgres.

The database stores metadata, object keys, extracted text versions, digests, and
relevance records. The original PDF or source file lives in object storage.

## Services

Start the RAG services:

```bash
docker compose -f docker-compose.rag.yml up -d
```

MinIO runs at:

- API: `http://localhost:9000`
- Console: `http://localhost:9001`
- Bucket: `sl-legal-corpus`

## Safe Dry Run

Use dry run before every new batch:

```bash
PYTHONPATH=rag uv run --with 'psycopg[binary]' --with boto3 \
  python scripts/sync_corpus_assets_to_object_storage.py \
  --scope manifest \
  --skip-existing-assets \
  --max-to-sync 500 \
  --progress-every 100 \
  --report-path data/indexes/object_storage_manifest_probe.jsonl
```

## Execute A Resumable Batch

Run bounded batches so a failure does not risk the full corpus:

```bash
PYTHONPATH=rag uv run --with 'psycopg[binary]' --with boto3 \
  python scripts/sync_corpus_assets_to_object_storage.py \
  --scope manifest \
  --skip-existing-assets \
  --max-to-sync 1000 \
  --batch-size 100 \
  --progress-every 100 \
  --execute \
  --report-path data/indexes/object_storage_manifest_execute_YYYYMMDDTHHMMSSZ.jsonl
```

Repeat the same command with a new report path. `--skip-existing-assets` makes
the run resume from the next unsynced manifest document.

For the current 113,358 downloaded records, continue batches until:

```sql
SELECT count(*) FROM documents WHERE primary_file_asset_id IS NOT NULL;
```

matches the downloaded manifest count that should be imported.

## Completed Full Manifest Load

The full downloaded manifest was synced on `2026-05-25T16:08:48Z`.

- Ingestion run: `object_asset_sync_manifest_full_20260525T153925Z`
- Downloaded manifest records processed: 113,358
- Newly synced originals: 113,156
- Already-present originals skipped: 202
- Failed records: 0
- Result report: `data/indexes/object_storage_manifest_full_20260525T153925Z.jsonl`
- Postgres original assets after run: 113,359
- MinIO object count after run: 113,462
- MinIO stored bytes after run: 162,068,220,626

There is one additional case-linked local document outside the downloaded
manifest, so the Postgres original-asset count is 113,359 while the downloaded
manifest count is 113,358.

## Include Extracted Text Versions

Only use this when page text has already been loaded into Postgres.

For normal production backfills, use the page-only text-version sync. It reads
the canonical `pages` table and does not rehash or recopy original PDFs:

```bash
PYTHONPATH=rag uv run --with 'psycopg[binary]' --with boto3 \
  python scripts/sync_text_versions_from_pages.py \
  --execute \
  --report-path data/indexes/text_version_sync_pages_YYYYMMDD.jsonl \
  --progress-every 1000 \
  --batch-size 500
```

This writes `document_text_versions`, extracted-text file assets, and
`extracted_full_text` digests.

The older `sync_corpus_assets_to_object_storage.py --include-text-versions`
path is still available when syncing originals and text versions together for a
small controlled batch.

## Translated Fallback Text

When no official English document exists, store English translation as a
derived fallback, never as replacement source text.

Required production labels:

- source-language extraction remains `text_origin='source'`;
- translated fallback is a separate `document_text_versions` row with
  `text_origin='translation'`;
- the translation row must carry `source_text_version_id`,
  `translated_from_language`, `translation_provider`, and
  `translation_review_status`;
- translated text assets use `asset_kind='translated_text'`;
- translated digests use `digest_type='translated_full_text'`;
- chunks created from translated text carry `text_origin='translation'`,
  `translated_text_fallback`, and, until lawyer-approved,
  `machine_translation_unreviewed`;
- when an official English document is later obtained, mark the translated row
  `translation_review_status='superseded_by_official'` and link
  `official_replacement_document_id`.

Use translated chunks only as recall/search fallback. Strategy generation and
citations must still point back to the original-language PDF and should warn
that the English text is translated unless it has been lawyer-approved.

## Page, Text, And Search Index Backfill

After PDF text extraction or OCR writes page JSONL artifacts, load them into
Postgres:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' \
  --with pydantic --with pydantic-settings --with eval-type-backport \
  python scripts/load_pages_postgres.py
```

Then create text versions and chunks:

```bash
PYTHONPATH=rag uv run --with 'psycopg[binary]' --with boto3 \
  python scripts/sync_text_versions_from_pages.py --execute

PYTHONPATH=rag uv run --with 'psycopg[binary]' \
  python scripts/build_rag_chunks_from_postgres.py \
  --include-gazettes \
  --include-translation-text-versions \
  --output data/indexes/rag_chunks_from_postgres_full_YYYYMMDD.jsonl
```

Load the resulting chunks into every search tier:

```bash
PYTHONPATH=rag uv run --with 'psycopg[binary]' \
  python scripts/load_rag_chunks_postgres.py \
  --mode psycopg \
  --chunks data/indexes/rag_chunks_from_postgres_full_YYYYMMDD.jsonl \
  --batch-size 5000

PYTHONPATH=rag uv run \
  python scripts/load_rag_chunks_opensearch.py \
  --chunks data/indexes/rag_chunks_from_postgres_full_YYYYMMDD.jsonl \
  --batch-size 1000

PYTHONPATH=rag uv run --with qdrant-client --with sentence-transformers \
  python scripts/load_rag_chunks_qdrant.py \
  --chunks data/indexes/rag_chunks_from_postgres_full_YYYYMMDD.jsonl \
  --provider sentence-transformers \
  --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --dimensions 384 \
  --batch-size 128 \
  --progress-every 10000 \
  --recreate
```

## Searchability Audit

A document is fully LLM-searchable only when it has all of these:

- a primary original file asset and original digest;
- at least one non-empty page in `pages`;
- a `current-pages-v1` row in `document_text_versions`;
- an extracted-text file asset and extracted-text digest;
- retrieval chunks in Postgres;
- matching chunk IDs in OpenSearch and Qdrant.

Generate the reusable audit after every extraction/indexing wave:

```bash
PYTHONPATH=rag uv run --with 'psycopg[binary]' \
  python scripts/audit_full_corpus_searchability.py
```

Current audit snapshot:

- Audit JSON: `data/tracking/rag_searchability/rag_searchability_audit_20260526_after_archive_index.json`
- Missing CSV: `data/tracking/rag_searchability/rag_searchability_missing_20260526_after_archive_index.csv`
- Fully searchable documents: 103,990
- Incomplete documents: 9,369
- Need page extraction, PDF repair, or redownload: 7,601
- Need OCR/text recovery: 1,768

Latest full searchable-layer index:

- Main chunk file: `data/indexes/rag_chunks_from_postgres_full_after_extract_20260526.jsonl`
- Supplemental Uva health statute chunk file: `data/indexes/rag_chunks_uva_health_statutes_20260526.jsonl`
- OCR supplemental chunk file: `data/indexes/rag_chunks_after_ocr_non_parl_acts_20260526.jsonl`
- Archive supplemental chunk file: `data/indexes/rag_chunks_after_archive_extract_20260526.jsonl`
- Postgres chunks: 1,573,476
- OpenSearch chunks: 1,573,476
- Qdrant chunks: 1,573,476

Latest PDF page extraction wave:

- Extractor: `scripts/extract_missing_pdf_pages_to_postgres.py`
- Full report: `data/indexes/pdf_text_extract_pages_full_20260526.jsonl`
- Failure CSV: `data/tracking/rag_searchability/pdf_text_extract_failures_20260526.csv`
- Processed: 99,999 documents
- Extracted text: 92,281 documents
- Empty text requiring OCR: 59 documents
- Unsupported file type: 62 documents
- Failed extraction, mostly malformed/truncated PDFs: 7,597 documents
- Pages upserted: 1,028,477

Latest OCR and archive recovery waves:

- Postgres OCR worker: `scripts/ocr_empty_pdf_pages_to_postgres.py`
- Non-Act OCR reports: `data/indexes/ocr_postgres_non_parl_acts_20260526.jsonl` and `data/indexes/ocr_postgres_remaining_non_parl_acts_20260526.jsonl`
- Archive extraction report: `data/indexes/archive_pdf_extract_pages_20260526.jsonl`
- Archive extraction recovered 58 archive records, loaded 77,431 pages, and extracted 152,327,604 characters.
- Remaining archive exceptions: 3 damaged archives and 1 archive with no text layer.

## Verification

Run the full quality gate after each sizeable batch:

```bash
PYTHONPATH=rag uv run --with fastapi --with httpx --with pydantic \
  --with pydantic-settings --with eval-type-backport --with sqlalchemy \
  --with 'psycopg[binary]' --with boto3 --with pillow --with pytest \
  python scripts/run_quality_checks.py --require-rag-indexes
```

Expected guarantees:

- Every imported document has a primary original file asset.
- Every imported document has an object-storage key and original SHA-256 digest.
- Every page-text-backed document has a current text version, text asset, text
  digest, and retrieval chunks.
- Postgres, OpenSearch, and Qdrant chunk IDs remain consistent.
