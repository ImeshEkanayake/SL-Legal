# SL Legal Assist Production Build Roadmap

**Product posture:** production-grade legal workbench, not an MVP.

**Product model:** a specialized Codex-like workspace for Sri Lankan legal work:
case navigation, legal chat, document viewing, source inspection, research-pack
generation, drafting, review, and lawyer-controlled actions in one interface.

**Core safety rule:** no legal answer, strategy, argument, counterargument, or
drafted legal conclusion may use uncited hidden knowledge. The LLM must work only
from the retrieved, cited Legal Research Pack for that matter.

---

## 1. Product Vision

Build a legal workbench that feels like Codex, but for lawyers.

The user should be able to:

- open a case workspace;
- view pleadings, judgments, statutes, gazettes, Hansard records, and evidence;
- chat with a legal assistant that can search, open, cite, compare, summarize,
  draft, and navigate;
- see every answer linked to exact source passages;
- move between cases, documents, research packs, tasks, drafts, and reviews;
- create strategy reports, counterarguments, submissions, chronologies, and
  issue maps;
- keep a full audit trail of what was retrieved, what was generated, and what a
  lawyer approved or rejected.

This is not a chatbot attached to a document store. It is a legal operating
environment.

---

## 2. UI Direction: Codex-Like Legal Workspace

The UI should follow the interaction model shown in the reference screenshot.
The goal is not a marketing page. The first screen is the working product.

### 2.1 Main Layout

```text
┌──────────────────────┬───────────────────────────┬──────────────────────────────┐
│ Project / Case Rail   │ Legal Chat / Agent Thread │ Document / Workspace Viewer  │
│                      │                           │                              │
│ New chat             │ User asks legal question  │ Tabs: PDF, judgment, statute │
│ Search               │ Agent plans/searches      │ OCR text, citation graph     │
│ Plugins / tools      │ Research pack summaries   │ Draft memo, diff, notes      │
│ Automations          │ Source-cited answers      │                              │
│                      │                           │                              │
│ Cases                │ Tool call trace           │ Source inspector             │
│ - Case A             │ Follow-up prompts         │ Page highlights              │
│ - Case B             │ Review warnings           │ Comments / annotations       │
│                      │                           │                              │
│ Data / corpus        │                           │                              │
│ Missing sources      │                           │                              │
└──────────────────────┴───────────────────────────┴──────────────────────────────┘
```

### 2.2 Required UI Capabilities

| Area | Required capabilities |
| --- | --- |
| Left rail | Projects, cases, recent chats, corpus dashboard, missing-source dashboard, automations, settings. |
| Chat pane | Codex-style conversational thread, tool traces, retrieval progress, citations, warnings, lawyer approval prompts. |
| Viewer pane | PDF viewer, OCR text viewer, markdown/docx viewer, statute/judgment structured view, source tabs. |
| Case workspace | Matter facts, parties, timeline, issues, evidence, uploaded documents, drafts, tasks, review status. |
| Source inspector | Exact page, paragraph, chunk, citation, authority level, source URL, OCR confidence, retrieval score. |
| Research pack view | Pack items, missing sources, retrieval trace, expand/re-run controls, pack version history. |
| Drafting workspace | Legal memo, submission, affidavit outline, argument map, counterargument table, citation checker. |
| Navigation | Open document from chat, jump to page, jump to citation, compare documents, return to case thread. |
| Interactions | Highlight source, add note, assign review, approve/reject AI claim, export pack/report. |
| Review workflow | Lawyer review queue, unresolved risks, citation validation, unsupported-claim warnings. |

### 2.3 UI Non-Negotiables

- The UI must be dense, calm, professional, and work-focused.
- The chat must be able to interact with documents and cases, not just answer text.
- Every citation in chat must open the exact source passage in the viewer.
- The document viewer and chat must stay synchronized.
- The user must be able to inspect what the agent did: query decomposition,
  retrieval results, selected pack items, rejected sources, and missing sources.
- No legal output should appear final until lawyer review status is recorded.

---

## 3. Production Architecture

```text
Client UI
  │
  ├── Case workspace API
  ├── Document viewer API
  ├── Chat / agent API
  ├── Research pack API
  └── Review / audit API

Backend services
  │
  ├── Identity, teams, roles, permissions
  ├── Case management service
  ├── Document ingestion service
  ├── OCR / extraction workers
  ├── Legal-unit segmentation workers
  ├── Hybrid retrieval service
  ├── Reranking service
  ├── Legal Research Pack service
  ├── LLM reasoning service
  ├── Draft/document generation service
  ├── Citation validation service
  ├── Audit logging service
  └── Notification / task service

Storage and indexes
  │
  ├── Object storage: PDFs, OCR text, thumbnails, exports
  ├── PostgreSQL: metadata, cases, packs, audit, review state
  ├── OpenSearch: BM25, phrase, fuzzy, filters
  ├── Qdrant/vector DB: dense and sparse semantic retrieval
  ├── Graph tables: citations, amendments, authority links
  ├── Redis: cache, sessions, jobs
  └── Queue: extraction, indexing, embedding, review jobs
```

---

## 4. Agent Architecture

Agents are allowed, but they must be bounded. Retrieval and legal truth do not
belong to an unconstrained agent.

### 4.1 Agent Chain

```text
Raw user query / case facts
        │
        ▼
MECE Case Structuring Agent
  - preserve raw input
  - split facts into atomic items
  - label explicit/inferred/ambiguous/missing/contradictory
  - map every item to source span
        │
        ▼
Retrieval Planning Agent
  - classify legal task
  - extract citations, statutes, courts, dates, parties
  - generate retrieval-only query variants
        │
        ▼
Hybrid Retrieval Service
  - exact lookup
  - BM25 / phrase / fuzzy
  - dense vector
  - sparse vector
  - citation graph
        │
        ▼
Reranker and Authority Scorer
        │
        ▼
Legal Research Pack Builder
        │
        ▼
Strategy / Drafting Agent
  - can use only pack items
  - every legal claim cites pack_item_id
        │
        ▼
Citation Validator and Lawyer Review
```

### 4.2 Agent Rules

- Structuring agents may organize facts, but must not answer law.
- Retrieval agents may propose queries, but must not invent authority.
- Drafting agents may reason only from the Legal Research Pack.
- Every agent output must be JSON-schema validated.
- Every extracted fact must point to a raw source span.
- Every legal claim must point to pack item IDs.
- Agent uncertainty must be explicit.

---

## 5. Build Phases

The phases overlap, but every module must pass its own quality gate before being
used by downstream features.

| Phase | Focus | Production output |
| --- | --- | --- |
| 0 | Product foundations | scope, safety rules, authority policy, review policy |
| 1 | Dev platform | repo structure, CI, environments, secrets, observability baseline |
| 2 | Data registry | corpus manifest, missing-source tracking, source reliability model |
| 3 | Extraction | text/OCR/layout pipeline, OCR quality scoring, manual review queue |
| 4 | Legal data model | documents, pages, legal units, chunks, citations, cases, packs |
| 5 | MECE case structuring | lossless case-fact decomposition with span preservation |
| 6 | Hybrid retrieval | exact, BM25, fuzzy, vector, sparse, graph retrieval |
| 7 | Reranking/evaluation | reranker, authority scoring, retrieval benchmark suite |
| 8 | Legal Research Pack | immutable pack generation, missing-source warnings, citation trace |
| 9 | LLM reasoning | pack-bounded answers, strategy, counterarguments, risk analysis |
| 10 | Case workspace UI | Codex-like project/case rail, chat, document viewer, source inspector |
| 11 | Drafting workflow | memos, submissions, issue maps, chronologies, citation checker |
| 12 | Review workflow | lawyer approval, claim validation, comments, audit trail |
| 13 | Security/compliance | auth, RBAC, encryption, tenant isolation, audit/export controls |
| 14 | Performance/load | ingestion load, retrieval latency, concurrent chat, viewer performance |
| 15 | Pilot hardening | lawyer beta, bug bash, red-team, production readiness |
| 16 | Production operations | monitoring, support process, update pipeline, continuous eval |

### Current Completion Status

| Phase | Status | Evidence |
| --- | --- | --- |
| 0 | Engineering implementation complete; production approval pending external legal signoff | `rag/sl_legal_rag/product_policy.py`, `tests/test_product_policy.py`, `Docs/phase_reviews/phase_0_product_foundations_review.md` |
| 1 | Backend/repo-owned implementation complete; production approval pending deployment/security process signoff | `scripts/run_quality_checks.py`, `scripts/check_no_plaintext_secrets.py`, `.github/workflows/quality.yml`, `Docs/phase_reviews/phase_1_dev_platform_review.md` |
| 2 | Engineering implementation complete for registry import and object-storage asset sync; production approval pending corpus/legal/licensing review | `rag/sl_legal_rag/data_registry.py`, `scripts/import_data_registry.py`, `scripts/sync_corpus_assets_to_object_storage.py`, `rag/sql/009_missing_source_registry.sql`, `rag/sql/011_object_storage_asset_tracking.sql`, `tests/test_data_registry.py`, `tests/test_object_storage_sync.py`, `Docs/phase_reviews/phase_2_data_registry_review.md` |
| 3 | Engineering implementation complete for extraction/OCR quality gates; production approval pending worker integration, load evidence, and manual QA | `rag/sl_legal_rag/extraction_quality.py`, `tests/test_extraction_quality.py`, `Docs/phase_reviews/phase_3_extraction_ocr_review.md` |
| 4 | Engineering implementation complete for legal data model and object-asset contracts; production approval pending performance/backup/operations review | `rag/sql/001_core.sql` through `rag/sql/011_object_storage_asset_tracking.sql`, `tests/test_schema_contracts.py`, `Docs/phase_reviews/phase_4_legal_data_model_review.md` |
| 5 | Engineering implementation complete for MECE structuring safeguards; production approval pending lawyer/domain sample review | `rag/sl_legal_rag/case_structure.py`, `tests/test_llm_agent_boundaries.py`, `Docs/phase_reviews/phase_5_mece_case_structuring_review.md` |
| 6 | Engineering implementation complete for hybrid retrieval contracts; production approval pending benchmark/performance/domain review | `rag/sl_legal_rag/exact_citation.py`, `rag/sl_legal_rag/hybrid_retrieval.py`, `rag/sl_legal_rag/retrieval.py`, `tests/test_exact_citation_resolver.py`, `tests/test_hybrid_retrieval.py`, `Docs/phase_reviews/phase_6_hybrid_retrieval_review.md` |
| 7 | Engineering implementation complete for retrieval evaluation metrics; production approval pending golden benchmark and reranker review | `rag/sl_legal_rag/retrieval_eval.py`, `tests/test_retrieval_eval.py`, `Docs/phase_reviews/phase_7_reranking_evaluation_review.md` |
| 8 | Engineering implementation complete for research-pack sealing, immutability, version lineage, traces, and expansion API; production approval pending legal/API/UX review | `rag/sl_legal_rag/research_pack.py`, `rag/sql/010_research_pack_contract.sql`, `tests/test_research_pack_contract.py`, `Docs/phase_reviews/phase_8_legal_research_pack_review.md` |
| 9 | Engineering implementation complete for pack-bounded reasoning, counterarguments, risk ranking, next-retrieval questions, prompt-injection blocking, and citation validation; production approval pending prompt/safety/lawyer review | `rag/sl_legal_rag/strategy.py`, `rag/sl_legal_rag/models.py`, `tests/test_strategy_reasoning.py`, `Docs/phase_reviews/phase_9_llm_reasoning_review.md` |
| 10 | Engineering implementation complete for the Codex-like case workspace UI, signed workspace API access, matter creation, chat persistence, tabbed document/pack/draft/review views, and browser smoke verification; production approval pending design/lawyer/load signoff | `rag/sl_legal_rag/api.py`, `rag/sl_legal_rag/db/repositories.py`, `web/src/components/CaseWorkspace.tsx`, `web/src/components/DocumentWorkspace.tsx`, `web/src/components/SourceInspector.tsx`, `web/src/components/CaseWorkspace.test.tsx`, `Docs/phase_reviews/phase_10_case_workspace_ui_review.md` |
| 11-16 | In progress / pending phase-by-phase completion | Each phase must receive implementation, tests, docs, and a review packet before being marked complete. |

### Current Corpus and RAG Snapshot

Updated: 2026-05-25T20:52:47Z

| Area | Current state |
| --- | --- |
| Raw corpus manifest | 147,625 rows tracked. |
| Downloaded corpus | 113,358 downloaded records, including 113,296 PDFs. |
| Corpus document store | 113,359 documents imported into Postgres: 113,358 downloaded manifest records plus 1 case-linked local document outside the downloaded manifest. |
| Fully LLM-searchable documents | 103,990 documents have non-empty pages, `current-pages-v1` text versions, retrieval chunks, and matching Postgres/OpenSearch/Qdrant index entries. |
| Incomplete documents | 9,369 documents are asset-tracked but not fully searchable yet. |
| Pending page extraction/repair | 7,601 documents need PDF repair, redownload, unsupported-format handling, or page extraction recovery. |
| Pending OCR/text recovery | 1,768 documents have page shells but no usable extracted text. |
| Page store | 1,927,382 page records loaded for 105,758 documents. |
| Text versions and digests | 103,990 current `document_text_versions` rows, 103,997 extracted-text assets, and 217,356 total `document_digests` rows. |
| Retrieval chunks | 1,573,476 chunks loaded in Postgres, OpenSearch, and Qdrant. |
| Index consistency | Clean: no missing or extra chunk IDs across Postgres, OpenSearch, and Qdrant. |
| Object storage | MinIO is running locally; 113,359/113,359 imported documents have original file assets, object keys, and original digests. |
| Stored assets | 217,356 tracked assets: 113,359 original document objects and 103,997 extracted-text objects. |
| Case relevance records | 0 rows because the current database has no linked `case_documents` rows yet; the sync path is ready to populate rows once case-document links exist. |
| Searchability audit | `data/tracking/rag_searchability/rag_searchability_audit_20260526_after_archive_index.json` and `data/tracking/rag_searchability/rag_searchability_missing_20260526_after_archive_index.csv`. |

Latest object-storage asset layer:

- Added MinIO to `docker-compose.rag.yml` as a local S3-compatible object store.
- Added object-storage configuration to `.env.example`.
- Added migration `rag/sql/011_object_storage_asset_tracking.sql`.
- Added `file_assets`, `document_text_versions`, `document_digests`, and `case_document_relevance`.
- Added object-storage pointers to `documents` and case-file asset linkage to `case_documents`.
- Added `scripts/sync_corpus_assets_to_object_storage.py` with dry-run mode, JSONL reports, resumable `--skip-existing-assets`, batch commits, progress output, ingestion-run traceability, and bounded `--max-to-sync` batch execution.
- Backfilled all 103 current searchable Postgres documents with original PDF assets, extracted-text assets, and SHA-256 digests.
- Hardened the RAG health gate so asset-only corpus records are allowed while page-backed/searchable documents still require chunks, text versions, and digests.
- Executed the first manifest scale batch: 100 new corpus originals copied from `data/raw` into MinIO and recorded in Postgres.
- Executed the full downloaded manifest sync: 113,358 downloaded records processed, 113,156 newly synced, 202 skipped as already present, 0 errors.
- Latest object sync run: `object_asset_sync_manifest_full_20260525T153925Z`, status `complete`, 113,358 processed rows, 0 errors.
- Added the operational runbook: `Docs/object_storage_asset_sync_runbook.md`.
- Loaded all existing extracted/OCR page artifacts into Postgres: 13,339 additional manifest documents, 818,802 additional pages, 0 missing-document skips.
- Added `scripts/sync_text_versions_from_pages.py` to build extracted-text MinIO objects, `document_text_versions`, and `extracted_full_text` digests from the canonical `pages` table without rehashing original PDFs.
- Added `scripts/extract_missing_pdf_pages_to_postgres.py` for resumable parallel PDF text extraction directly into the `pages` table, with JSONL reporting, ingestion events, status updates, pypdf primary extraction, and pypdfium2 fallback.
- Ran the full PDF page extraction backfill: 99,999 candidates processed, 92,281 documents extracted, 1,028,477 pages upserted, 59 empty-text OCR candidates, 62 unsupported files, and 7,597 malformed/truncated PDF extraction failures tracked in `data/tracking/rag_searchability/pdf_text_extract_failures_20260526.csv`.
- Synced text versions from page text after extraction: 103,871 current text-backed documents, 103,871 extracted-text assets, and 103,871 extracted-text digests.
- Built the full Postgres-backed chunk file: `data/indexes/rag_chunks_from_postgres_full_after_extract_20260526.jsonl`, plus supplemental `data/indexes/rag_chunks_uva_health_statutes_20260526.jsonl`.
- Indexed 1,507,702 chunks for 103,871 documents into Postgres, OpenSearch, and Qdrant using the multilingual `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` embedding model.
- Added `scripts/audit_full_corpus_searchability.py` plus reusable CSV/JSON tracking for documents that still need page extraction or OCR.
- Added `scripts/ocr_empty_pdf_pages_to_postgres.py` for Postgres-native Tesseract OCR recovery with ingestion-run traceability, page confidence, OCR artifacts, and canonical `pages` upserts.
- Ran non-Act OCR recovery and indexed 61 newly text-backed documents with 645 chunks.
- Added ZIP archive support to `scripts/extract_missing_pdf_pages_to_postgres.py`.
- Ran archive extraction for Lankalaw/court/provincial archives: 58 archive records extracted, 77,431 pages upserted, 152,327,604 characters extracted, and 65,129 chunks indexed.
- Current full-corpus blocker: 9,369 downloaded/asset-tracked documents remain incomplete and must pass OCR, PDF repair, redownload, or unsupported-format handling before they can be called LLM-searchable.

Latest completed corpus wave:

- Source: `SC_OFFICIAL`
- Wave file: `data/indexes/sc_official_wave_20260525T102633Z_document_ids.txt`
- Documents processed: 50
- Pages loaded: 459
- Retrieval chunks created: 394
- OCR documents completed in the wave: 15
- Chunk output: `data/indexes/sc_official_wave_20260525T102633Z_rag_chunks.jsonl`

Latest remediation slice:

- Added a production RAG health gate: `scripts/check_rag_production_health.py`.
- Wired the health gate into `scripts/run_quality_checks.py`; strict local mode also checks OpenSearch and Qdrant.
- Re-ran OCR for `parl_act_1950_043_g5240` (`Industrial Disputes Act, No. 43 of 1950`): 30/30 pages, high confidence, 60,871 characters.
- Rebuilt `parl_act_1950_043_g5240` into 28 official OCR-backed retrieval chunks.
- Invalidated the old browser-smoke research pack/chunk whose seed text was not supported by recovered OCR text.
- Added a Postgres-backed chunk builder for case-linked documents whose UI/document IDs do not exist in the raw corpus manifest: `scripts/build_rag_chunks_from_postgres.py`.
- Indexed `doc_c6fd17ba78f9402285a23bdcd97ddbe6` from Postgres page text with 2 retrieval chunks.
- Re-ran OCR for `sc_judgment_695ccde778e92_9r3_3c14968bf4`, loaded the recovered page text, and indexed it with low-confidence OCR flags.
- Normalized low-confidence OCR flags so retrieval and research-pack policy recognize both current and legacy flag names.
- Fixed chunk upserts so quality flags update on re-index.

Latest ingestion/search quality gate:

- Targeted Python tests for the new/changed ingestion and audit paths: 23 passed.
- RAG production health gate: passed.
- Strict search-index consistency gate: passed.
- The previous full app quality gate remains recorded for UI/build/security checks; this wave did not modify the web app.

---

## 6. Phase Details and Quality Gates

### Phase 0: Product Foundations

**Build**

- Product scope and prohibited-use policy.
- Authority hierarchy.
- Source reliability model.
- Legal output risk levels.
- Human review workflow.

**Tests**

- Policy rule tests for prohibited outputs.
- Citation-required output tests.
- Missing-source behavior tests.

**Review gate**

- Legal review of product boundaries.
- Engineering review of enforceability.
- No downstream LLM work starts until these rules are encoded.

### Phase 1: Dev Platform

**Build**

- Backend, frontend, worker, and infrastructure repositories or monorepo layout.
- CI/CD pipeline.
- Local Docker Compose stack.
- Environment configuration.
- Secrets management.
- Error logging and tracing.

**Tests**

- Unit test runner.
- Integration test runner.
- E2E test runner.
- Static analysis.
- Type checks.
- Security dependency scan.

**Review gate**

- Code review on CI, test layout, environment reproducibility, and rollback plan.

### Phase 2: Data Registry

**Build**

- Canonical document registry.
- Downloaded/missing/licensed/blocked status tracking.
- Source reliability fields.
- File hash and version tracking.
- Ingestion run registry with per-document extraction/indexing event evidence.
- Data tracking dashboards.

**Tests**

- Manifest import tests.
- Duplicate detection tests.
- Missing-source classification tests.
- Hash/version regression tests.

**Review gate**

- Data model review.
- Corpus tracking review.
- Sampling review against actual file tree.

### Phase 3: Extraction and OCR

**Build**

- PDF text extraction.
- OCR fallback.
- Layout-aware extraction for complex PDFs.
- Page-level JSONL output.
- OCR confidence scoring.
- Low-confidence review queue.

**Tests**

- Unit tests for extractors and parsers.
- Golden PDF extraction tests.
- OCR quality regression tests.
- Page count and text hash tests.
- Fuzz tests for corrupted PDFs.

**Load tests**

- Batch extraction throughput.
- Worker retry and failure handling.
- Large-PDF memory usage.

**Review gate**

- Code review per extractor.
- Manual QA sample for each document category.
- No low-confidence OCR silently enters legal answers.

### Phase 4: Legal Data Model

**Build**

- `documents`, `pages`, `legal_units`, `retrieval_chunks`, `citations`,
  `research_packs`, `research_pack_items`, `cases`, `case_documents`,
  `case_facts`, ingestion traceability tables, and audit tables.

**Tests**

- Migration tests.
- Data integrity tests.
- Foreign-key and cascade tests.
- Idempotent re-index tests.

**Review gate**

- Database schema review.
- Query performance review.
- Backup/restore review.

### Phase 5: MECE Case Structuring

**Build**

- Case-fact structuring agent.
- Atomic fact list.
- Party extraction.
- Timeline extraction.
- Issue candidates.
- Missing facts.
- Contradictions.
- Source-span mapping.

**Tests**

- JSON schema validation.
- Span preservation tests.
- No-fact-loss tests using fixture narratives.
- Contradiction detection tests.
- Ambiguity labeling tests.

**Review gate**

- Prompt review.
- Schema review.
- Lawyer review of sample decompositions.

### Phase 6: Hybrid Retrieval

**Build**

- Exact citation resolver.
- Act/section/provision resolver.
- Case-name resolver.
- OpenSearch BM25, phrase, and fuzzy search.
- Qdrant dense vector search.
- Sparse retrieval candidate path.
- Citation graph expansion.

**Tests**

- Exact citation lookup tests.
- Fuzzy search typo tests.
- Semantic match tests.
- Filter tests by year, court, source, authority level.
- Missing-source tests.

**Load tests**

- Index build time.
- Query latency under concurrent users.
- Large corpus search throughput.

**Review gate**

- Retrieval code review.
- Index mapping review.
- Benchmark review before LLM integration.

### Phase 7: Reranking and Evaluation

**Build**

- Reciprocal Rank Fusion.
- Cross-encoder reranker.
- Authority scoring.
- OCR/source-quality penalties.
- Golden legal retrieval set.
- Metrics dashboard.

**Tests**

- Recall@20.
- MRR.
- nDCG@10.
- Citation accuracy.
- Regression tests for known questions.

**Review gate**

- Retrieval quality review.
- No strategy-generation release unless retrieval benchmark passes.

### Phase 8: Legal Research Pack

**Build**

- Immutable pack IDs.
- Pack versioning.
- Pack item scoring.
- Missing-source warnings.
- Retrieval trace.
- Expand/re-run workflow.

**Tests**

- Pack immutability tests.
- Citation trace tests.
- Token budget tests.
- Unsupported-source rejection tests.

**Review gate**

- Legal pack contract review.
- API review.
- UX review of pack inspector.

### Phase 9: LLM Reasoning

**Build**

- Pack-bounded answer generation.
- Strategy report generation.
- Counterargument simulation.
- Risk ranking.
- Next-retrieval question generation.
- Citation validator.

**Tests**

- No-citation no-claim tests.
- Fabricated citation tests.
- Prompt injection tests.
- Missing authority tests.
- Regression tests against golden packs.

**Review gate**

- Prompt review.
- Safety review.
- Lawyer review of generated samples.

### Phase 10: Codex-Like Case Workspace UI

**Build**

- Project/case sidebar.
- Chat thread.
- Tool progress messages.
- Document viewer tabs.
- Source inspector.
- Case file explorer.
- Search panel.
- Pack viewer.
- Draft viewer.

**Tests**

- Component unit tests.
- E2E navigation tests.
- Accessibility tests.
- PDF/document viewer tests.
- Citation click-through tests.
- Responsive layout tests.

**Load tests**

- Large PDF open performance.
- Multiple open tabs.
- Long chat thread performance.
- Concurrent document viewers.

**Review gate**

- UI code review.
- Design review against Codex-like reference.
- Lawyer workflow review.

### Phase 11: Drafting Workflow

**Build**

- Legal memo draft.
- Written submission draft.
- Argument map.
- Chronology.
- Evidence table.
- Authorities table.
- Export to docx/pdf/markdown.

**Tests**

- Draft structure tests.
- Citation preservation tests.
- Export tests.
- Redline/diff tests.

**Review gate**

- Lawyer review.
- Export format review.
- Citation checker review.

### Phase 12: Lawyer Review Workflow

**Build**

- Claim approval/rejection.
- Inline comments.
- Review tasks.
- Review status per pack/draft.
- Audit log.

**Tests**

- Permission tests.
- Review state transition tests.
- Audit immutability tests.
- Multi-user conflict tests.

**Review gate**

- Security review.
- Legal workflow review.

### Phase 13: Security and Compliance

**Build**

- Authentication.
- RBAC.
- Case-level permissions.
- Encryption in transit and at rest.
- Tenant isolation if multi-tenant.
- PII/client confidential data controls.
- Audit export.

**Tests**

- Auth tests.
- Authorization bypass tests.
- Tenant isolation tests.
- Secrets scanning.
- Penetration test.

**Review gate**

- Security review.
- Privacy review.
- Deployment review.

### Phase 14: Performance and Load

**Build**

- Load test harness.
- Observability dashboards.
- SLOs for chat, retrieval, viewer, ingestion, and export.
- Queue backpressure and retry policy.

**Tests**

- Concurrent chat users.
- Concurrent retrieval users.
- Indexing while serving queries.
- OCR/extraction job load.
- Large case workspace load.
- Failure recovery tests.

**Review gate**

- Performance review.
- Capacity plan.
- Incident response plan.

### Phase 15: Production Pilot

**Build**

- Controlled lawyer pilot.
- Feedback capture.
- Known limitation banners.
- Support process.
- Bug triage process.

**Tests**

- End-to-end pilot scenarios.
- Red-team legal hallucination tests.
- Disaster recovery test.
- Backup restore test.

**Review gate**

- Go/no-go review.
- Legal signoff.
- Security signoff.
- Engineering signoff.

### Phase 16: Production Operations

**Build**

- Continuous corpus updates.
- Continuous retrieval evals.
- Model/version registry.
- Monitoring and alerting.
- Support dashboards.
- Incident retrospectives.

**Tests**

- Scheduled regression tests.
- Corpus update tests.
- Model upgrade tests.
- Data drift checks.

**Review gate**

- Monthly retrieval quality review.
- Monthly security review.
- Quarterly legal policy review.

---

## 7. Testing Strategy

Every subsection, subcategory, and main function must have tests at the correct
level before code review is complete.

### 7.1 Required Test Types

| Test type | Purpose |
| --- | --- |
| Unit tests | Validate small functions, parsers, scoring functions, UI components. |
| Integration tests | Validate API + database + search + vector DB + workers together. |
| End-to-end tests | Validate full user workflows from UI to answer/export. |
| Retrieval evals | Validate legal search quality against golden questions. |
| LLM safety tests | Validate no uncited claims, no fabricated citations, no hidden source usage. |
| Load tests | Validate latency, throughput, concurrency, and memory usage. |
| Security tests | Validate permissions, isolation, secrets, injection resistance. |
| Regression tests | Ensure fixed bugs never return. |
| Snapshot/golden tests | Protect structured outputs and generated pack formats. |
| Manual lawyer QA | Validate legal usefulness and source correctness. |

### 7.2 Minimum Quality Bar

No feature is considered done unless:

- unit tests pass;
- integration tests pass for affected services;
- E2E test exists for user-facing workflows;
- load/performance impact is measured for heavy paths;
- security impact is reviewed where permissions or client data are touched;
- code review is complete;
- documentation is updated;
- telemetry/logging exists for production debugging;
- rollback or migration plan exists if the feature changes data.

---

## 8. Code Review Process

Every subsection and main function gets a review gate.

### 8.1 Review Levels

| Review level | Applies to | Required reviewers |
| --- | --- | --- |
| Function review | Core algorithms, parsers, prompts, validators | senior engineer |
| Module review | Extraction, retrieval, pack builder, UI viewer, drafting | senior engineer + domain reviewer if legal logic |
| Security review | Auth, permissions, case data, uploads, exports | security-minded engineer |
| Legal review | Authority ranking, legal output policy, generated examples | qualified lawyer/domain expert |
| UX review | Chat, viewer, case workspace, review workflow | product/design reviewer |
| Performance review | Retrieval, OCR, indexing, viewer, chat streaming | backend/performance reviewer |

### 8.2 PR Checklist

Every PR must answer:

- What legal/product risk does this change affect?
- What data does it read/write?
- What tests were added?
- What load/performance behavior changed?
- What user workflow was verified?
- What logs/metrics were added?
- Could this produce an uncited or wrong legal output?
- How is rollback handled?

---

## 9. Production Readiness Gates

### Gate A: Data Foundation Ready

- Corpus registry is stable.
- Missing-source tracker is visible.
- Extraction quality is measured.
- Low-confidence OCR is blocked or flagged.

### Gate B: Retrieval Ready

- Exact citation lookup passes.
- Hybrid retrieval passes benchmark.
- Reranking improves or preserves metrics.
- Missing-source detection works.

### Gate C: Legal Research Pack Ready

- Pack items are immutable.
- Every pack item opens exact source passage.
- Every pack has retrieval trace and version.
- Pack can be expanded without losing audit history.

### Gate D: LLM Reasoning Ready

- LLM cannot access sources outside pack.
- Unsupported legal claims are rejected.
- Citation hallucination tests pass.
- Prompt injection tests pass.

### Gate E: UI Ready

- Codex-like case workspace works end to end.
- Chat and viewer are synchronized.
- Documents open from citations.
- Review states are visible.
- Large documents and long chats remain performant.

### Gate F: Pilot Ready

- Security review passed.
- Load tests passed.
- Disaster recovery tested.
- Lawyer pilot scripts passed.
- Known limitations are documented.

---

## 10. First Implementation Sequence

The first production slice should prove the entire architecture on a narrow but
real workflow.

1. Create case workspace data model.
2. Build MECE case structuring schema and validator.
3. Build chunk/index loaders for PostgreSQL, OpenSearch, and Qdrant.
4. Implement exact citation/provision resolver.
5. Implement hybrid retrieval service.
6. Implement Legal Research Pack API.
7. Build pack inspector UI.
8. Build Codex-like three-pane shell.
9. Wire chat to create and inspect research packs.
10. Add citation click-through into document viewer.
11. Add answer generation from pack only.
12. Add citation validator.
13. Add review queue.
14. Add tests and load tests for the full flow.
15. Run code review and lawyer review before expanding scope.

The first vertical workflow:

```text
Create case
  → paste facts
  → MECE case structure
  → retrieve authorities
  → create Legal Research Pack
  → inspect source documents
  → generate cited legal research answer
  → validate citations
  → lawyer approves/rejects claims
```

---

## 11. Non-Goals Until Core Is Stable

- No autonomous legal filing.
- No uncited answer mode.
- No strategy generation before retrieval eval passes.
- No broad gazette indexing until core search is stable.
- No prediction presented as certainty.
- No training on confidential client data without explicit policy and consent.

---

## 12. Current Immediate Next Step

Build the first vertical production slice:

1. backend schemas for cases, case facts, packs, and review states;
2. MECE case structuring agent contract;
3. real hybrid retrieval endpoint;
4. Codex-like UI shell with case rail, chat pane, and document viewer pane;
5. test harness covering unit, integration, E2E, load, and citation safety.

This slice should be treated as production foundation work intended to remain
part of the final system.
