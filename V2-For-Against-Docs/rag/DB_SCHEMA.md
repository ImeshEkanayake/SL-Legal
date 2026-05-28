# SL Legal Assist Database Schema

The database layer is built before the app so the UI, agents, retrieval service,
and review workflow all write to stable contracts.

## Schema Files

| File | Purpose |
| --- | --- |
| `rag/sql/001_core.sql` | Corpus, pages, legal units, retrieval chunks, citations, embeddings, research packs, missing sources, retrieval events. |
| `rag/sql/002_workspace_cases.sql` | Organizations, users, projects, cases, permissions, parties, case documents, raw inputs, MECE facts, timeline, issues, evidence. |
| `rag/sql/003_chat_agents_review.sql` | Chat threads, messages, agent runs, tool calls, pack links, legal claims, citations, annotations, drafts, review items, tasks, jobs, audit events. |
| `rag/sql/004_source_anchors.sql` | Durable page-level source anchors for cited research-pack items. |
| `rag/sql/005_audit_indexes.sql` | Cursor-pagination indexes for case, user, organization, event-type, and entity audit streams. |
| `rag/sql/006_api_rate_limits.sql` | Fixed-window API rate limits for expensive signed AI and retrieval routes. |
| `rag/sql/007_operational_metric_rollups.sql` | Daily operational metric rollups for compliance reporting. |
| `rag/sql/008_ingestion_traceability.sql` | Traceable ingestion runs, per-document extraction events, and current document ingest state. |
| `rag/sql/009_missing_source_registry.sql` | Missing-source registry metadata for corpus tracking imports. |
| `rag/sql/010_research_pack_contract.sql` | Immutable research-pack metadata, version lineage, token counts, source warnings, scoring details, and retrieval traces. |
| `rag/sql/011_object_storage_asset_tracking.sql` | S3-compatible file assets, object storage pointers, full-text versions, document digests, and case-document relevance. |
| `rag/sql/012_translation_text_fallbacks.sql` | Explicit translated-text fallback provenance for source text versions, object assets, digests, and retrieval chunks. |
| `rag/sql/013_research_pack_payload.sql` | Sealed canonical research-pack payload storage so strategy drafting reloads server-persisted packs by ID. |
| `rag/sql/014_embedding_index_metadata.sql` | Vector embedding model, dimensions, Qdrant collection, and source metadata for compatibility checks. |
| `rag/sql/015_case_document_relevance_indexes.sql` | Case-document relevance uniqueness and pack-score lookup indexes for retrieval confidence surfacing. |
| `rag/sql/016_document_summary_search.sql` | Document-level short summaries for cheaper high-recall search prefiltering before full chunk retrieval. |

## Apply Schema

```bash
python3 scripts/apply_postgres_schema.py
```

This starts only the Postgres container and applies all SQL files in order.

## Check Schema

```bash
python3 scripts/check_postgres_schema.py
```

## Smoke Test Relationships

```bash
python3 scripts/smoke_test_postgres_schema.py
```

The smoke test creates an organization, user, project, case, MECE fact, chat
thread, agent run, research pack, legal claim, draft, review item, task, job, and
audit event inside one transaction, checks the links, and rolls everything back.

## Operations Maintenance

```bash
uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with eval-type-backport \
  python scripts/prune_api_rate_limits.py
uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with eval-type-backport \
  python scripts/rebuild_operational_rollups.py --date YYYY-MM-DD
```

This deletes old `api_rate_limits` rows after
`SL_LEGAL_RATE_LIMIT_RETENTION_SECONDS`, defaulting to seven days. The rollup
script rebuilds one day of durable compliance metrics from `audit_events` and
`api_rate_limits`.

## Backend Access Layer

The app-facing repository layer lives in `rag/sl_legal_rag/db/`.

```bash
uv run --with sqlalchemy --with 'psycopg[binary]' scripts/smoke_test_db_access_layer.py
uv run --with pytest --with sqlalchemy --with 'psycopg[binary]' \
  --with-editable rag pytest tests/test_db_access_layer.py
```

The smoke test uses the live Postgres database but rolls back the transaction.

## Main Data Areas

### Corpus And Retrieval

- `documents`
- `document_versions`
- `file_assets`
- `document_text_versions`
- `document_digests`
- `ingestion_runs`
- `document_ingestion_events`
- `pages`
- `legal_units`
- `retrieval_chunks`
- `citations`
- `embedding_runs`
- `research_packs`
- `research_pack_items`
- `missing_sources`
- `retrieval_events`

### Workspace And Cases

- `organizations`
- `app_users`
- `organization_memberships`
- `projects`
- `cases`
- `case_permissions`
- `case_parties`
- `case_documents`
- `case_raw_inputs`
- `case_facts`
- `case_fact_sources`
- `case_timeline_events`
- `case_issues`
- `case_evidence_items`
- `case_document_relevance`

### Codex-Like Chat And Agent Work

- `chat_threads`
- `chat_messages`
- `agent_runs`
- `agent_steps`
- `tool_calls`

### Legal Review And Drafting

- `case_research_packs`
- `legal_claims`
- `legal_claim_citations`
- `document_annotations`
- `drafts`
- `review_items`
- `app_tasks`

### Operations

- `background_jobs`
- `audit_events`
- `api_rate_limits`
- `operational_metric_rollups`
- `schema_migrations`

## Design Rules

- The LLM never reads raw PDFs directly.
- Every legal claim must cite `research_pack_items`.
- Original extracted source-language text must never be replaced by translation text.
- Translations are stored as derived `document_text_versions` with `text_origin='translation'`, source-version lineage, provider/model metadata, review status, and replacement links for later official English documents.
- Retrieval chunks created from translations must carry `text_origin='translation'` and translation review status so strategy generation can warn and prefer official source text when available.
- Every case fact extracted from user input should preserve source span metadata.
- Every document viewer action should be traceable to document/page/chunk IDs.
- Every document ingestion attempt should create immutable event evidence and
  update the current `documents` state.
- Every research pack should be sealed with a canonical hash, token count,
  source warnings, and retrieval trace; later expansion creates a linked child
  pack rather than rewriting the parent.
- Review state is stored separately from generated content so lawyers can approve,
  reject, or comment without mutating the original generation.
