# V2 Codebase Map

## Repository Shape

V2 is contained in:

```text
V2-For-Against-Docs/
```

Core folders:

- `rag/`: backend package, SQL schema, retrieval, strategy, policy, and API code.
- `scripts/`: operational scripts, ingestion scripts, quality gates, index loaders, and smoke checks.
- `tests/`: backend unit and integration tests.
- `web/`: Next.js case workspace UI.
- `Docs/`: product, architecture, data, testing, and phase-review documentation.
- `data_tracking/`: lightweight notes only in Git; generated tracking data is handled through the data plan.

## Backend Package

Main package:

```text
rag/sl_legal_rag/
```

Important modules:

- `api.py`: FastAPI endpoints for research packs, strategy, cases, review, drafts, claims, audit, and workspace data.
- `models.py`: Pydantic contracts for case structuring, research packs, strategy drafts, review queues, claims, and workspace responses.
- `strategy.py`: pack-bounded strategy prompt construction, draft generation, and citation validation.
- `research_pack.py`: research pack sealing, hashing, token accounting, and contract validation.
- `case_structure.py`: MECE case structuring prompts and validation.
- `hybrid_retrieval.py`: OpenSearch and Qdrant hybrid retrieval orchestration.
- `two_stage_retrieval.py`: two-stage recall and precision flow.
- `retrieval.py`: local and generic retrieval support.
- `exact_citation.py`: exact citation and provision resolution.
- `source_anchoring.py`: source text anchoring and quote location.
- `product_policy.py`: product safety policy checks.
- `auth.py`: signed request authentication.
- `metrics.py`: operational metric helpers.
- `db/repositories.py`: persistence layer for cases, packs, documents, drafts, claims, review, audit, and source context.
- `db/session.py`: database session setup.
- `llm/azure_openai.py`: Azure OpenAI provider integration.

## SQL Schema

Schema files live in:

```text
rag/sql/
```

Current foundations:

- `001_core.sql`: documents, retrieval chunks, research packs, and missing sources.
- `002_workspace_cases.sql`: organizations, projects, cases, facts, issues, evidence, and case documents.
- `003_chat_agents_review.sql`: chat, agent runs, legal claims, claim citations, annotations, drafts, review items, tasks, jobs, and audit.
- `004_source_anchors.sql`: source anchors for pack items.
- `010_research_pack_contract.sql`: pack versioning, hashes, token counts, and trace metadata.
- `011_object_storage_asset_tracking.sql`: assets, text versions, digests, and case document relevance.
- `013_research_pack_payload.sql`: sealed pack payload storage.
- `015_case_document_relevance_indexes.sql`: case document relevance indexes.

V2 stance work should add a reviewed migration plan before changing schema.

## Frontend

Frontend folder:

```text
web/
```

Important files:

- `web/src/app/page.tsx`: workspace entry.
- `web/src/app/actions.ts`: server actions that call backend APIs.
- `web/src/components/CaseWorkspace.tsx`: main workspace shell.
- `web/src/components/DocumentWorkspace.tsx`: documents, research pack, drafts, and review panels.
- `web/src/components/SourceInspector.tsx`: citation and source context panel.
- `web/src/components/PdfDocumentViewer.tsx`: PDF rendering.
- `web/src/lib/workspace-types.ts`: TypeScript workspace contracts.
- `web/src/lib/workspace-api.ts`: API client helpers.
- `web/src/lib/ui-session*.ts`: UI session signing support.

V2 UI work should add strategy memo first views, evidence stance grouping, and review actions beside support/adverse/mixed evidence.

## Operational Scripts

Quality and safety:

- `scripts/run_quality_checks.py`: full backend and frontend quality gate.
- `scripts/check_no_plaintext_secrets.py`: secret scanner.
- `scripts/check_postgres_schema.py`: schema compatibility check.
- `scripts/smoke_test_postgres_schema.py`: rollback-only schema smoke test.
- `scripts/check_rag_production_health.py`: RAG health check.
- `scripts/run_detached_quality_gate.sh`: detached test and quality runner.

Retrieval and index operations:

- `scripts/build_rag_chunks.py`
- `scripts/build_rag_chunks_from_postgres.py`
- `scripts/load_rag_chunks_postgres.py`
- `scripts/load_rag_chunks_opensearch.py`
- `scripts/load_rag_chunks_qdrant.py`
- `scripts/query_hybrid_retrieval.py`
- `scripts/run_two_stage_recall_precision_checks.py`
- `scripts/run_production_benchmark_gates.py`

Data and corpus operations:

- `scripts/acquire_*`
- `scripts/extract_*`
- `scripts/sync_*`
- `scripts/audit_full_corpus_searchability.py`
- `scripts/create_data_tracking.py`

## Test Suite

Backend tests live in:

```text
tests/
```

Current coverage includes:

- schema contracts
- research pack contracts
- strategy reasoning
- source anchoring
- exact citation
- API research pack endpoint
- hybrid retrieval
- RAG index pipeline
- production health
- object storage sync
- case file cache security
- data registry
- extraction quality

V2 must add stance-specific tests for support, adverse, mixed, and context evidence.

Frontend tests live beside frontend code:

```text
web/src/**/*.test.ts
web/src/**/*.test.tsx
```

## V2 Expansion Points

Recommended additions:

- `ClaimEvidenceAssessment` models in `rag/sl_legal_rag/models.py`.
- Evidence assessment prompt and validation helpers in `rag/sl_legal_rag/strategy.py` or a new focused module.
- Repository methods in `rag/sl_legal_rag/db/repositories.py`.
- API endpoints in `rag/sl_legal_rag/api.py`.
- Strategy memo and evidence stance UI in `web/src/components`.
- Tests in `tests/test_evidence_stance.py`, `tests/test_strategy_reasoning.py`, API tests, and UI tests.

## Data Boundary

The large `data/` corpus is local and outside Git. Generated tracking CSVs are also outside normal Git. Keep the directory structure stable and publish manifests/checksums through the future data plan.
