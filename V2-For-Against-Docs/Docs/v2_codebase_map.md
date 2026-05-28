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
- `models.py`: Pydantic contracts for case structuring, research packs, strategy drafts, reasoning packs, review queues, claims, and workspace responses.
- `strategy.py`: pack-bounded strategy prompt construction, reasoning-pack draft generation, and citation validation.
- `research_pack.py`: research pack sealing, hashing, token accounting, and contract validation.
- `case_structure.py`: MECE case structuring prompts and validation.
- `hybrid_retrieval.py`: OpenSearch and Qdrant hybrid retrieval orchestration.
- `adverse_retrieval.py`: V2 supportive/adverse query expansion, query-intent tagging, and adverse retrieval scoring.
- `two_stage_retrieval.py`: two-stage recall and precision flow.
- `retrieval.py`: local and generic retrieval support.
- `exact_citation.py`: exact citation and provision resolution.
- `source_anchoring.py`: source text anchoring and quote location.
- `product_policy.py`: product safety policy checks.
- `auth.py`: signed request authentication.
- `metrics.py`: operational metric helpers.
- `operations.py`: Phase 6 load scenario parsing, token substitution, percentile summaries, threshold evaluation, and Phase 7 operational plans.
- Phase 8 support in `operations.py`: readiness evidence requirements, detached log and JSON report evaluation, blocker classification, and deployment decision packs.
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
- `web/src/app/actions.ts`: server actions that call backend APIs for cases, messages, and review decisions.
- `web/src/components/CaseWorkspace.tsx`: main workspace shell.
- `web/src/components/DocumentWorkspace.tsx`: documents, research pack, reasoning pack, and review panels.
- `web/src/components/SourceInspector.tsx`: citation, reasoning, and source context panel.
- `web/src/components/PdfDocumentViewer.tsx`: PDF rendering.
- `web/src/lib/workspace-types.ts`: TypeScript workspace and reasoning-pack contracts.
- `web/src/lib/workspace-api.ts`: API client helpers for signed workspace and review calls.
- `web/src/lib/ui-session*.ts`: UI session signing support.

V2 UI work should add reasoning pack first views, evidence stance grouping, and review actions beside support/adverse/mixed evidence.

## Operational Scripts

Quality and safety:

- `scripts/run_quality_checks.py`: full backend and frontend quality gate.
- `scripts/check_no_plaintext_secrets.py`: secret scanner.
- `scripts/check_postgres_schema.py`: schema compatibility check.
- `scripts/smoke_test_postgres_schema.py`: rollback-only schema smoke test.
- `scripts/check_rag_production_health.py`: RAG health check.
- `scripts/run_detached_quality_gate.sh`: detached test and quality runner.
- `scripts/run_phase6_load_tests.py`: signed concurrent API load runner for Phase 6 workspace, retrieval, strategy validation, source, and review paths.
- `scripts/run_phase7_operational_plan.py`: renders the Phase 7 release, deployment, hosted-data, and monitoring command manifest.
- `scripts/run_phase7_monitoring_snapshot.py`: writes or executes the Phase 7 recurring monitoring snapshot.
- `scripts/run_phase8_readiness_pack.py`: builds local or production-stack deployment readiness evidence packs.

Retrieval and index operations:

- `scripts/build_rag_chunks.py`
- `scripts/build_rag_chunks_from_postgres.py`
- `scripts/load_rag_chunks_postgres.py`
- `scripts/load_rag_chunks_opensearch.py`
- `scripts/load_rag_chunks_qdrant.py`
- `scripts/query_hybrid_retrieval.py`
- `scripts/run_two_stage_recall_precision_checks.py`
- `scripts/run_production_benchmark_gates.py`
- `scripts/run_v2_for_against_retrieval_eval.py`

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

V2 must keep stance-specific tests for support, adverse, mixed, and context evidence and reasoning-pack tests for lawyer-review outputs.

Frontend tests live beside frontend code:

```text
web/src/**/*.test.ts
web/src/**/*.test.tsx
```

## V2 Expansion Points

Recommended additions:

- `ClaimEvidenceAssessment` models in `rag/sl_legal_rag/models.py`.
- Evidence assessment repository methods in `rag/sl_legal_rag/db/repositories.py`.
- Evidence assessment API endpoints in `rag/sl_legal_rag/api.py`.
- Reasoning pack and evidence stance UI in `web/src/components`.
- Tests in `tests/test_evidence_assessments.py`, `tests/test_db_access_layer.py`, API tests, and future UI tests.

## V2 Phase 2 Evidence Assessment Contract

Phase 2 adds a claim-level evidence assessment contract without applying a database migration. The active implementation uses:

- `rag/sl_legal_rag/models.py`: `EvidenceStance`, `ClaimEvidenceAssessmentRequest`, `ClaimEvidenceAssessment`, grouped response models, and stance-to-citation-role mapping.
- `rag/sl_legal_rag/db/repositories.py`: create, list, and grouped retrieval methods backed by `legal_claims`, `legal_claim_citations`, `research_pack_items`, and `retrieval_chunks`.
- `rag/sl_legal_rag/api.py`: signed create/list endpoints at `/v1/cases/{case_id}/evidence/assessments`.
- `Docs/v2_phase_2_evidence_assessment_contract.md`: API, validation, persistence, review, and future migration contract.

## V2 Phase 3 Adverse Retrieval Contract

Phase 3 adds retrieval-layer for/against coverage without changing the database. The active implementation uses:

- `rag/sl_legal_rag/adverse_retrieval.py`: deterministic query variants for supportive, adverse, limitation, exception, and procedural-risk intents.
- `rag/sl_legal_rag/hybrid_retrieval.py`: executes intent-tagged OpenSearch and Qdrant searches for each query variant.
- `rag/sl_legal_rag/retrieval.py`: preserves query intents and query variant IDs through fusion, selected pack item traces, metadata, and scoring breakdowns.
- `rag/sl_legal_rag/retrieval_eval.py`: reports supportive and adverse recall separately and enforces adverse cases in blind fixtures.
- `rag/evals/v2_for_against_retrieval_fixture.json`: CI-safe fixture for support/adverse recall behavior.
- `Docs/v2_phase_3_adverse_retrieval_contract.md`: query intent, trace, scoring, evaluation, and release boundaries.

## V2 Phase 4 Reasoning Pack Contract

Phase 4 adds the production reasoning layer without changing the database schema. The active implementation uses:

- `rag/sl_legal_rag/models.py`: `AuthorityVerification`, `IssueMatrixItem`, `LegalElement`, `FactLawMapping`, `ForAgainstArgument`, `PreliminaryLegalOpinion`, `LawyerReviewPack`, and `ReasoningPackOutput`.
- `rag/sl_legal_rag/strategy.py`: requested output support for `for_against_brief`, `preliminary_legal_opinion`, and `lawyer_review_pack`, plus reasoning-pack citation and cautious-language validation.
- `rag/sl_legal_rag/db/repositories.py`: stores structured reasoning output in `drafts.metadata.reasoning_pack`, human-readable output in `drafts.content_markdown`, and review items for adverse reasoning and missing evidence.
- `rag/sl_legal_rag/api.py`: returns `reasoning_review_item_ids` from strategy draft generation.
- `tests/test_reasoning_pack_models.py`: schema and validator coverage.
- `tests/test_strategy_reasoning.py`: generation and pack-bounded citation coverage.
- `tests/test_db_access_layer.py`: integration coverage for persistence, draft detail metadata, review queue items, and audit.
- `Docs/v2_phase_4_reasoning_pack_contract.md`: output structure, storage boundary, validation rules, and release scope.

## V2 Phase 5 Production UI Contract

Phase 5 adds the lawyer-facing reasoning pack workspace without changing the database schema. The active implementation uses:

- `rag/sl_legal_rag/models.py`: `WorkspaceDraftSummary` exposes `requestedOutput` and `reasoningPack`.
- `rag/sl_legal_rag/db/repositories.py`: workspace draft summaries read `reasoning_pack` from existing draft metadata.
- `web/src/lib/workspace-types.ts`: TypeScript reasoning-pack, preliminary opinion, review decision, and workspace contracts.
- `web/src/lib/workspace-api.ts`: signed review decision client for `/v1/cases/{case_id}/review/items/{review_item_id}/decision`.
- `web/src/app/actions.ts`: `recordReviewDecisionAction`.
- `web/src/components/CaseWorkspace.tsx`: reasoning navigation and local review item status updates.
- `web/src/components/DocumentWorkspace.tsx`: reasoning pack detail, citation navigation, and review decision controls.
- `web/src/components/SourceInspector.tsx`: reasoning rail summary.
- `web/src/components/CaseWorkspace.test.tsx`: UI tests for reasoning view, citation navigation, and review actions.
- `Docs/v2_phase_5_production_ui_contract.md`: UI contract, safety rules, tests, and release boundary.

## V2 Phase 6 Production Operations Contract

Phase 6 adds the production operations package without changing the database schema. The active implementation uses:

- `rag/evals/phase6_load_scenarios.json`: canonical API load scenario fixture for workspace, research, strategy validation, source viewer, and review queue paths.
- `rag/sl_legal_rag/operations.py`: load scenario schema parsing, recursive placeholder substitution, p50/p95/p99 summaries, error-rate calculation, and threshold status.
- `scripts/run_phase6_load_tests.py`: signed load runner for local or staging APIs with dry-run and real-load modes.
- `scripts/run_detached_quality_gate.sh`: `load-plan` and `load` detached modes with PID/log files.
- `Docs/v2_phase_6_production_operations_contract.md`: service-level targets, observability, release gate, and safety boundaries.
- `Docs/v2_phase_6_operations_runbook.md`: release, metrics, incident, rollback, corpus audit, and data hydration workflow.
- `tests/test_phase6_operations.py`: contract coverage for scenario fixture, token substitution, threshold enforcement, and fixture schema.

## V2 Phase 7 Deployment And Monitoring Contract

Phase 7 makes deployment readiness and corpus monitoring repeatable without changing the database schema. The active implementation uses:

- `rag/evals/phase7_deployment_monitoring_manifest.json`: reviewed command manifest for release gates, deployment readiness, hosted data, and recurring monitoring.
- `rag/sl_legal_rag/operations.py`: operational manifest loading, command validation, rendered command lines, and plan output.
- `scripts/run_phase7_operational_plan.py`: JSON, shell, and Markdown operational plan renderer.
- `scripts/run_phase7_monitoring_snapshot.py`: monitoring snapshot planner and controlled executor.
- `tests/test_phase7_operations.py`: manifest coverage, production-stack flags, command rendering, plan rendering, and monitoring snapshot evidence tests.
- `Docs/v2_phase_7_deployment_monitoring_contract.md`: deployment and monitoring contract.
- `Docs/v2_phase_7_hosted_data_strategy.md`: hosted data strategy and no-raw-Git boundary.

## V2 Phase 8 Deployment Readiness Evidence Contract

Phase 8 adds an evidence-backed deployment decision layer without changing the database schema. The active implementation uses:

- `rag/evals/phase8_deployment_readiness_evidence.json`: required local-release and production-stack evidence manifest.
- `rag/sl_legal_rag/operations.py`: evidence requirement validation, evidence evaluation, blocker detection, and readiness pack generation.
- `scripts/run_phase8_readiness_pack.py`: command-line pack builder for local release and production-stack evidence.
- `scripts/run_detached_quality_gate.sh`: `readiness-pack` and `readiness-pack-production` detached modes.
- `tests/test_phase8_readiness_pack.py`: manifest coverage, ready decision, missing production evidence, and script-output tests.
- `Docs/v2_phase_8_readiness_evidence_contract.md`: readiness evidence contract.
- `Docs/v2_phase_8_readiness_runbook.md`: evidence collection and cutover review workflow.

## Data Boundary

The large `data/` corpus is local and outside Git. Generated tracking CSVs are also outside normal Git. Keep the directory structure stable and publish manifests/checksums through the future data plan.
