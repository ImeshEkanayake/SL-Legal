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
- `models.py`: Pydantic contracts for case structuring, research packs, strategy drafts, reasoning packs, agentic research plans, matter memory, review queues, claims, and workspace responses.
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
- Phase 9 support in `operations.py`: release artifact manifests, file checksums, missing artifact classification, and artifact report generation.
- Phase 10 support in `operations.py`: release publication manifests, allowed-path checks, publication plans, and asset SHA-256 verification.
- Phase 11 support in `operations.py`: GitHub release asset digest normalization, remote/local asset comparison, and verification reports.
- Phase 12 support in `operations.py`: release provenance manifests, GitHub release checks, tag commit checks, evidence checksums, and ledger generation.
- Phase 13 support in `operations.py`: release attestation manifests, subject digest evaluation, in-toto-style statements, and deterministic attestation digests.
- Phase 14 support in `operations.py`: signing readiness manifests, approved signing mode validation, forbidden private-key scans, and signing-readiness reports.
- Phase 15 support in `operations.py`: signing plan manifests, artifact checksum evaluation, non-mutating signing command plans, and verification command templates.
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
- `scripts/build_phase9_release_artifacts.py`: builds release artifact checksum reports and optional evidence bundles.
- `scripts/publish_phase10_release_assets.py`: plans or executes approved GitHub release asset publication.
- `scripts/verify_phase11_release_assets.py`: verifies published GitHub release assets against approved local checksums and sizes.

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

## V2 Phase 9 Release Artifact Contract

Phase 9 adds a release artifact packaging layer without changing the database schema. The active implementation uses:

- `rag/evals/phase9_release_artifacts_manifest.json`: approved local and production-stack artifact manifest.
- `rag/sl_legal_rag/operations.py`: artifact manifest validation, SHA-256 checksums, missing-required detection, and artifact report generation.
- `scripts/build_phase9_release_artifacts.py`: report writer and optional tarball builder.
- `scripts/run_detached_quality_gate.sh`: `artifact-report` and `artifact-report-production` detached modes.
- `tests/test_phase9_release_artifacts.py`: artifact manifest, checksum, missing-required, and bundle tests.
- `Docs/v2_phase_9_release_artifact_contract.md`: artifact contract.
- `Docs/v2_phase_9_release_artifact_runbook.md`: artifact generation and attachment workflow.

## V2 Phase 10 Release Asset Publication Contract

Phase 10 adds controlled GitHub release asset publication without changing the database schema. The active implementation uses:

- `rag/evals/phase10_release_asset_publication.json`: approved asset publication manifest.
- `rag/sl_legal_rag/operations.py`: publication manifest validation, allowed-path enforcement, SHA-256 checksums, and plan generation.
- `scripts/publish_phase10_release_assets.py`: dry-run publication planner and explicit `--execute` uploader.
- `scripts/run_detached_quality_gate.sh`: `asset-publication-plan` detached mode.
- `tests/test_phase10_release_publication.py`: target release, ready asset, blocked asset, and script-output tests.
- `Docs/v2_phase_10_release_asset_publication_contract.md`: publication contract.
- `Docs/v2_phase_10_release_asset_publication_runbook.md`: publication workflow.

## V2 Phase 11 Published Asset Verification Contract

Phase 11 adds post-publication release asset verification without changing the database schema. The active implementation uses:

- `rag/sl_legal_rag/operations.py`: remote asset digest normalization, remote/local comparison, mismatch detection, and verification reports.
- `scripts/build_phase9_release_artifacts.py`: deterministic release bundle writer used by the verification gate.
- `scripts/verify_phase11_release_assets.py`: GitHub release asset verification runner.
- `scripts/run_detached_quality_gate.sh`: `asset-verification` detached mode.
- `tests/test_phase9_release_artifacts.py`: deterministic bundle regression coverage.
- `tests/test_phase11_release_asset_verification.py`: verification, mismatch, saved payload, and manifest tests.
- `Docs/v2_phase_11_published_asset_verification_contract.md`: verification contract.
- `Docs/v2_phase_11_published_asset_verification_runbook.md`: verification workflow.

## V2 Phase 12 Release Provenance Ledger Contract

Phase 12 adds a release provenance ledger without changing the database schema. The active implementation uses:

- `rag/evals/phase12_release_provenance.json`: required provenance evidence for the latest completed release.
- `rag/sl_legal_rag/operations.py`: provenance manifest validation, release metadata checks, tag commit comparison, evidence checksums, and ledger construction.
- `scripts/build_phase12_release_provenance.py`: GitHub/git metadata collector and ledger writer.
- `scripts/run_detached_quality_gate.sh`: `release-provenance` detached mode.
- `tests/test_phase12_release_provenance.py`: verified, missing, draft-release, saved-metadata, and manifest tests.
- `Docs/v2_phase_12_release_provenance_contract.md`: provenance contract.
- `Docs/v2_phase_12_release_provenance_runbook.md`: provenance workflow.

## V2 Phase 13 Release Attestation Envelope Contract

Phase 13 adds checksum-backed release attestation envelopes without changing the database schema. The active implementation uses:

- `rag/evals/phase13_release_attestation.json`: required attestation subjects for the latest completed release.
- `rag/sl_legal_rag/operations.py`: attestation manifest validation, subject digest evaluation, in-toto-style statement construction, and canonical attestation digesting.
- `scripts/build_phase13_release_attestation.py`: GitHub/git metadata collector and attestation writer.
- `scripts/run_detached_quality_gate.sh`: `release-attestation` detached mode.
- `tests/test_phase13_release_attestation.py`: verified, deterministic digest, failed-ledger, saved-metadata, and manifest tests.
- `Docs/v2_phase_13_release_attestation_contract.md`: attestation contract.
- `Docs/v2_phase_13_release_attestation_runbook.md`: attestation workflow.

## V2 Phase 14 Release Signing Readiness Contract

Phase 14 adds a release signing readiness gate without changing the database schema. The active implementation uses:

- `rag/evals/phase14_release_signing_readiness.json`: approved signing modes, forbidden private-key globs, execution requirements, and required evidence.
- `rag/sl_legal_rag/operations.py`: signing-readiness manifest validation, release metadata checks, tag commit checks, attestation evidence checksums, approved-mode validation, and forbidden-key scans.
- `scripts/build_phase14_signing_readiness.py`: GitHub/git metadata collector and signing-readiness report writer.
- `scripts/run_detached_quality_gate.sh`: `signing-readiness` detached mode.
- `tests/test_phase14_signing_readiness.py`: ready report, forbidden-key, unsupported-mode, saved-metadata, and manifest tests.
- `Docs/v2_phase_14_release_signing_readiness_contract.md`: signing-readiness contract.
- `Docs/v2_phase_14_release_signing_readiness_runbook.md`: signing-readiness workflow.

## V2 Phase 15 Release Signing Execution Plan Contract

Phase 15 adds a non-mutating release signing execution plan without changing the database schema. The active implementation uses:

- `rag/evals/phase15_release_signing_plan.json`: target release, signing mode, readiness report, signature output directory, and signing artifacts.
- `rag/sl_legal_rag/operations.py`: signing plan manifest validation, artifact checksum evaluation, release/tag checks, readiness report checks, and signing/verification command templates.
- `scripts/build_phase15_signing_plan.py`: GitHub/git metadata collector and signing plan writer.
- `scripts/run_detached_quality_gate.sh`: `signing-plan` detached mode.
- `tests/test_phase15_signing_plan.py`: planned report, missing-artifact, unready-readiness, saved-metadata, and manifest tests.
- `Docs/v2_phase_15_release_signing_plan_contract.md`: signing-plan contract.
- `Docs/v2_phase_15_release_signing_plan_runbook.md`: signing-plan workflow.

## V2 Phase 16 Agentic Research Workflow Foundation

Phase 16 adds the Maat-informed agentic research foundation without changing the database schema. The active implementation uses:

- `rag/sl_legal_rag/models.py`: `AgentToolTrace`, `AuthorityExpansionCandidate`, `ClarificationNeed`, `MatterMemory`, and `AgentResearchPlan`.
- `tests/test_agentic_research_models.py`: source-boundary, sequencing, clarification, authority-promotion, and matter-memory validator coverage.
- `Docs/v2_phase_16_agentic_research_contract.md`: tool router, source boundary, authority candidate, clarification, matter-memory, and plan sequencing contract.
- `Docs/releases/v2_phase_16_agentic_research_foundation.md`: release note and local validation evidence.

## V2 Phase 17 Lawyer Review Pack Validation

Phase 17 validates the post-roadmap reasoning path for the first tuned scenario without changing the database schema. The active implementation uses:

- `scripts/run_phase17_lawyer_review_pack_validation.py`: builds a bounded validation pack from the Phase 16 retrieval report and generates `requested_output="lawyer_review_pack"`.
- `rag/sl_legal_rag/strategy.py`: retries once with a repair prompt when model output fails pack-boundary validation.
- `tests/test_strategy_reasoning.py`: covers repair of uncited legal-claim sentences.
- `Docs/releases/v2_phase_17_lawyer_review_pack_validation.md`: validation release note and local evidence summary.

## V2 Phase 18 Agentic Backend Metadata Integration

Phase 18 connects the agentic research foundation to the existing strategy-draft backend without changing the database schema. The active implementation uses:

- `rag/sl_legal_rag/agentic_research.py`: deterministic `AgentResearchPlan` and `MatterMemory` bundle builder.
- `rag/sl_legal_rag/api.py`: `/v1/strategy/draft` creates the agentic bundle after pack-bounded draft validation.
- `rag/sl_legal_rag/db/repositories.py`: `persist_strategy_draft` stores `agentic_research_plan` and `matter_memory` in existing draft and chat-message metadata.
- `tests/test_agentic_research_service.py`: service-level route, candidate, matter-memory, and clarification coverage.
- `tests/test_api_research_pack_endpoint.py`: API handoff coverage for agentic metadata.
- `tests/test_db_access_layer.py`: draft detail metadata coverage.
- `Docs/v2_phase_18_agentic_backend_metadata_contract.md`: backend metadata contract and boundaries.
- `Docs/releases/v2_phase_18_agentic_backend_metadata.md`: release note and validation evidence.

## V2 Phase 19 Agentic Workspace Visibility

Phase 19 exposes the agentic backend metadata in the lawyer workspace without changing the database schema. The active implementation uses:

- `rag/sl_legal_rag/models.py`: `WorkspaceDraftSummary` exposes `agenticResearchPlan` and `matterMemory`.
- `rag/sl_legal_rag/db/repositories.py`: workspace draft summaries read agentic metadata from existing draft metadata.
- `web/src/lib/workspace-types.ts`: TypeScript contracts for agent tool traces, authority candidates, clarification needs, agentic plans, and matter memory.
- `web/src/components/DocumentWorkspace.tsx`: Reasoning tab agentic workflow panel for tool route, clarification blockers, authority candidates, and matter memory.
- `web/src/components/CaseWorkspace.test.tsx`: UI rendering coverage for agentic workflow metadata.
- `tests/test_db_access_layer.py`: backend workspace snapshot coverage for agentic metadata.
- `Docs/v2_phase_19_agentic_workspace_contract.md`: agentic workspace contract and UI safety boundaries.
- `Docs/releases/v2_phase_19_agentic_workspace.md`: release note and validation evidence.

## V2 Phase 20 Agentic Review Queue Actions

Phase 20 makes agentic metadata actionable through the existing review queue without changing the database schema. The active implementation uses:

- `rag/sl_legal_rag/db/repositories.py`: creates and handles `clarification_need` and `authority_candidate` review items.
- `tests/test_db_access_layer.py`: integration coverage for new review item creation, listing, decisions, and audit events.
- `web/src/components/CaseWorkspace.test.tsx`: UI fixture and rendering coverage for the new review item types.
- `Docs/v2_phase_20_agentic_review_queue_contract.md`: review item contract and decision boundaries.
- `Docs/releases/v2_phase_20_agentic_review_queue.md`: release note and validation evidence.

## V2 Phase 21 Authority Pack Expansion Planning

Phase 21 converts approved authority-candidate reviews into draft metadata that can drive a later research-pack expansion, while candidate authorities remain non-citable. The active implementation uses:

- `rag/sl_legal_rag/models.py`: `AuthorityPackExpansionPlan` schema and validation boundaries.
- `rag/sl_legal_rag/agentic_research.py`: deterministic builder for official-source expansion requests.
- `rag/sl_legal_rag/db/repositories.py`: review approval hook that stores expansion plans and audit metadata.
- `web/src/lib/workspace-types.ts`: workspace types for expansion plans.
- `web/src/components/DocumentWorkspace.tsx`: reasoning workspace display for planned expansion queries.
- `tests/test_agentic_research_models.py`: non-citable and official-source schema coverage.
- `tests/test_agentic_research_service.py`: builder coverage.
- `tests/test_db_access_layer.py`: persistence and audit integration coverage.
- `web/src/components/CaseWorkspace.test.tsx`: UI visibility coverage.
- `Docs/v2_phase_21_authority_pack_expansion_contract.md`: planning contract and future execution boundary.
- `Docs/releases/v2_phase_21_authority_pack_expansion_planning.md`: release note and validation evidence.

## V2 Phase 22 Authority Pack Expansion Execution

Phase 22 executes planned authority expansion requests through the existing research-pack expansion flow and records child pack metadata without promoting authorities. The active implementation uses:

- `rag/sl_legal_rag/models.py`: execution records and endpoint response schema.
- `rag/sl_legal_rag/api.py`: execution endpoint for planned authority expansion requests.
- `rag/sl_legal_rag/db/repositories.py`: metadata persistence for child pack execution records.
- `web/src/lib/workspace-types.ts`: workspace types for execution records.
- `web/src/components/DocumentWorkspace.tsx`: display of executed child pack IDs.
- `tests/test_agentic_research_models.py`: execution metadata validation coverage.
- `tests/test_api_research_pack_endpoint.py`: API endpoint execution coverage.
- `tests/test_db_access_layer.py`: repository metadata integration coverage.
- `Docs/v2_phase_22_authority_pack_expansion_execution_contract.md`: execution contract and promotion boundary.
- `Docs/releases/v2_phase_22_authority_pack_expansion_execution.md`: release note and validation evidence.

## V2 Phase 23 Authority Expansion Idempotency

Phase 23 fixes authority expansion execution race conditions from review. The active implementation uses:

- `rag/sl_legal_rag/db/repositories.py`: locked draft metadata reads for execution recording and duplicate checks.
- `rag/sl_legal_rag/api.py`: locked duplicate re-check before execution metadata is recorded.
- `tests/test_api_research_pack_endpoint.py`: duplicate execution conflict coverage.
- `Docs/v2_phase_23_authority_expansion_idempotency_contract.md`: locking contract and remaining reservation boundary.
- `Docs/releases/v2_phase_23_authority_expansion_idempotency.md`: release note and validation evidence.

## V2 Phase 24 Authority Expansion Reservation

Phase 24 prevents duplicate authority expansion retrieval by reserving a request before child pack creation. The active implementation uses:

- `rag/sl_legal_rag/models.py`: reservation records on `AuthorityPackExpansionPlan`.
- `rag/sl_legal_rag/db/repositories.py`: locked reservation, completion, and failure metadata updates.
- `rag/sl_legal_rag/api.py`: pre-retrieval reservation before research-pack expansion.
- `web/src/lib/workspace-types.ts`: workspace reservation record type.
- `web/src/components/CaseWorkspace.test.tsx`: fixture coverage for reservation metadata shape.
- `tests/test_agentic_research_models.py`: reservation validation coverage.
- `tests/test_api_research_pack_endpoint.py`: duplicate reservation conflict coverage.
- `tests/test_db_access_layer.py`: reservation-to-completion persistence coverage.
- `Docs/v2_phase_24_authority_expansion_reservation_contract.md`: reservation contract.
- `Docs/releases/v2_phase_24_authority_expansion_reservation.md`: release note and validation evidence.

## V2 Phase 25 Child Pack Source Anchoring and Authority Verification

Phase 25 verifies executed authority expansion child packs before any candidate authority can be promoted. The active implementation uses:

- `rag/sl_legal_rag/models.py`: `authority_pack_verification.v1` and per-item verification records.
- `rag/sl_legal_rag/db/repositories.py`: locked child-pack verification and draft metadata persistence.
- `rag/sl_legal_rag/api.py`: child-pack verification endpoint and audit event.
- `web/src/lib/workspace-types.ts`: frontend verification record types.
- `web/src/components/DocumentWorkspace.tsx`: verification status display for authority expansion plans.
- `web/src/components/CaseWorkspace.test.tsx`: fixture coverage for verification metadata shape.
- `tests/test_agentic_research_models.py`: verification boundary validation.
- `tests/test_api_research_pack_endpoint.py`: verification endpoint coverage.
- `tests/test_db_access_layer.py`: execution-to-verification persistence coverage.
- `Docs/v2_phase_25_child_pack_authority_verification_contract.md`: verification contract.
- `Docs/releases/v2_phase_25_child_pack_authority_verification.md`: release note and validation evidence.

## V2 Phase 26 Controlled Authority Promotion

Phase 26 promotes only verified authority expansion child-pack items into citable matter-memory references. The active implementation uses:

- `rag/sl_legal_rag/models.py`: `authority_pack_promotion.v1` request, item, record, and response contracts.
- `rag/sl_legal_rag/db/repositories.py`: locked promotion persistence and matter-memory candidate updates.
- `rag/sl_legal_rag/api.py`: child-pack promotion endpoint and audit event.
- `web/src/lib/workspace-types.ts`: frontend promotion record types.
- `web/src/components/DocumentWorkspace.tsx`: promotion status display for authority expansion plans.
- `web/src/components/CaseWorkspace.test.tsx`: fixture coverage for promotion metadata shape.
- `tests/test_agentic_research_models.py`: promotion validation coverage.
- `tests/test_api_research_pack_endpoint.py`: promotion endpoint coverage.
- `tests/test_db_access_layer.py`: verification-to-promotion persistence coverage.
- `Docs/v2_phase_26_controlled_authority_promotion_contract.md`: promotion contract.
- `Docs/releases/v2_phase_26_controlled_authority_promotion.md`: release note and validation evidence.

## V2 Phase 27 Full 10-Case Verification and Promotion Validation

Phase 27 validates V2 across the full tuned 10-case set after the authority verification and promotion path is available. The active implementation uses:

- `scripts/run_two_stage_recall_precision_checks.py`: full 10-case two-stage retrieval report generation.
- `scripts/run_phase27_full_case_validation.py`: aggregate lawyer-review and promotion-readiness scoring.
- `scripts/run_phase17_lawyer_review_pack_validation.py`: reused pack construction and deterministic lawyer-review pack generation.
- `rag/evals/two_stage_tuned_cases.json`: 10-case tuned validation source.
- `rag/sl_legal_rag/db/repositories.py`: official Gazette verification boundary fix.
- `tests/test_phase17_validation_runner.py`: Phase 27 aggregate runner and promotion-readiness tests.
- `tests/test_agentic_research_models.py`: official Gazette promotion validation.
- `Docs/v2_phase_27_full_case_validation_contract.md`: validation contract.
- `Docs/releases/v2_phase_27_full_case_validation.md`: release note and validation evidence.

## V2 Phase 28 Authority Workflow UI Integration

Phase 28 wires the existing authority expansion, verification, and promotion backend into the lawyer workspace UI without changing the database schema. The active implementation uses:

- `web/src/lib/workspace-types.ts`: frontend input, response, verification, and promotion contracts for authority workflow actions.
- `web/src/lib/workspace-api.ts`: signed backend clients for authority expansion execution, child-pack verification, and controlled promotion.
- `web/src/app/actions.ts`: server actions that call the signed clients and revalidate the workspace.
- `web/src/app/page.tsx`: passes authority workflow actions into the workspace shell.
- `web/src/components/CaseWorkspace.tsx`: local draft-plan state updates and refresh after authority workflow actions.
- `web/src/components/DocumentWorkspace.tsx`: reasoning-panel controls for `Execute`, `Verify`, and `Promote`, plus child-pack verification and promotion summaries.
- `web/src/components/CaseWorkspace.test.tsx`: UI coverage for the full Execute -> Verify -> Promote path.
- `Docs/v2_phase_28_authority_workflow_ui_contract.md`: UI integration contract.
- `Docs/releases/v2_phase_28_authority_workflow_ui.md`: release note and validation evidence.

## V2 Phase 29 Browser Workflow Validation

Phase 29 adds repeatable browser evidence for the authority workflow UI without using the shared database or raw corpus. The active implementation uses:

- `web/scripts/run-phase29-browser-workflow.mjs`: starts a temporary signed local backend, starts the real Next app, launches system Chrome through Playwright Core, and clicks Execute -> Verify -> Promote.
- `web/package.json`: `phase29:e2e` script for local browser workflow validation.
- `web/package-lock.json`: locks `playwright-core` for deterministic browser automation without bundled browser downloads.
- `scripts/run_detached_quality_gate.sh`: `phase29-browser-workflow` detached mode.
- `logs/phase29-browser-workflow`: ignored local evidence output containing screenshot, JSON report, Markdown summary, and Next dev log.
- `Docs/v2_phase_29_browser_workflow_validation_contract.md`: browser validation contract.
- `Docs/releases/v2_phase_29_browser_workflow_validation.md`: release note and validation evidence.

## V2 Phase 30 UI Deployment Readiness

Phase 30 adds a non-mutating readiness gate for deploying the V2 lawyer workspace UI after browser validation. The active implementation uses:

- `rag/evals/phase30_ui_deployment_readiness.json`: readiness manifest for Phase 29 evidence and hosted UI environment requirements.
- `rag/sl_legal_rag/operations.py`: `load_ui_deployment_readiness_manifest` and `build_ui_deployment_readiness_report`.
- `scripts/build_phase30_ui_deployment_readiness.py`: report builder for local and hosted environment readiness.
- `scripts/run_detached_quality_gate.sh`: `ui-deployment-readiness` and `ui-deployment-readiness-env` detached modes.
- `tests/test_phase30_ui_deployment_readiness.py`: coverage for manifest loading, evidence validation, hosted secret checks, dev-only blockers, and CLI output.
- `.env.example`: local UI environment variable examples.
- `Docs/v2_phase_30_ui_deployment_readiness_contract.md`: readiness contract.
- `Docs/v2_phase_30_ui_deployment_readiness_runbook.md`: operator runbook.
- `Docs/releases/v2_phase_30_ui_deployment_readiness.md`: release note and validation evidence.

## V2 Phase 31 Staging Cutover Dry Run

Phase 31 adds a non-mutating staging cutover dry-run gate for the V2 lawyer workspace UI. The active implementation uses:

- `rag/evals/phase31_staging_cutover_dry_run.json`: cutover manifest with required reports, smoke commands, approvals, and rollback steps.
- `rag/sl_legal_rag/operations.py`: `load_staging_cutover_dry_run_manifest` and `build_staging_cutover_dry_run`.
- `scripts/build_phase31_staging_cutover_dry_run.py`: report builder for local and hosted staging dry runs.
- `scripts/run_detached_quality_gate.sh`: `staging-cutover-dry-run` detached mode.
- `tests/test_phase31_staging_cutover_dry_run.py`: coverage for accepted Phase 30 statuses, missing evidence blockers, rollback validation, and CLI output.
- `Docs/v2_phase_31_staging_cutover_dry_run_contract.md`: cutover contract.
- `Docs/v2_phase_31_staging_cutover_dry_run_runbook.md`: operator runbook.
- `Docs/releases/v2_phase_31_staging_cutover_dry_run.md`: release note and validation evidence.

## V2 Phase 32 Hosted Staging Execution Pack

Phase 32 adds a hosted staging execution pack for running the V2 lawyer workspace UI in staging with private reviewer access. The active implementation uses:

- `rag/evals/phase32_hosted_staging_execution.json`: execution manifest with required reports, hosted execution steps, approvals, and rollback steps.
- `rag/sl_legal_rag/operations.py`: `load_hosted_staging_execution_manifest` and `build_hosted_staging_execution_pack`.
- `scripts/build_phase32_hosted_staging_execution_pack.py`: report builder for local and hosted staging execution packs.
- `scripts/create_ui_session_token.py`: private signed session cookie utility for hosted staging review.
- `scripts/run_detached_quality_gate.sh`: `hosted-staging-execution-pack` detached mode.
- `tests/test_phase32_hosted_staging_execution_pack.py`: coverage for execution-pack states, blockers, CLI output, and token shape.
- `Docs/v2_phase_32_hosted_staging_execution_contract.md`: execution contract.
- `Docs/v2_phase_32_hosted_staging_execution_runbook.md`: operator runbook.
- `Docs/releases/v2_phase_32_hosted_staging_execution.md`: release note and validation evidence.

## V2 Phase 33 Hosted Staging Execution Validation

Phase 33 adds the hosted staging validation gate that consumes real platform evidence. The active implementation uses:

- `rag/evals/phase33_hosted_staging_validation.json`: validation manifest with prerequisites and required hosted evidence.
- `rag/sl_legal_rag/operations.py`: `load_hosted_staging_validation_manifest` and `build_hosted_staging_validation_report`.
- `scripts/build_phase33_hosted_staging_validation.py`: report builder for local pending and hosted validated states.
- `scripts/run_detached_quality_gate.sh`: `hosted-staging-validation` detached mode.
- `tests/test_phase33_hosted_staging_validation.py`: coverage for pending local evidence, complete hosted evidence, blockers, and CLI output.
- `Docs/v2_phase_33_hosted_staging_validation_contract.md`: validation contract.
- `Docs/v2_phase_33_hosted_staging_validation_runbook.md`: operator runbook.
- `Docs/releases/v2_phase_33_hosted_staging_validation.md`: release note and validation evidence.

## Data Boundary

The large `data/` corpus is local and outside Git. Generated tracking CSVs are also outside normal Git. Keep the directory structure stable and publish manifests/checksums through the future data plan.
