# V2 Production Product Roadmap

## Product Standard

V2 is a production legal evidence intelligence system, not a prototype. The product must identify, explain, cite, and review evidence that supports, weakens, contradicts, or contextualizes a client's legal position. The system must be safe for lawyer review workflows, auditable from answer back to source page, measurable under load, and documented well enough for another engineer to operate it.

## North Star

For every matter, V2 produces a lawyer-review reasoning pack that separates:

- Arguments for the client.
- Adverse material against the client.
- Mixed authorities that help on one issue and hurt on another.
- Context-only material.
- Missing authorities and next retrieval questions.
- Missing client evidence, procedural evidence, and lawyer verification tasks.
- A preliminary legal opinion draft with explicit lawyer-verification qualification.

Every legal statement must trace to a sealed research pack item, source citation, page anchor, quality status, and reviewer decision.

## Core Principles

- Claim-level stance is authoritative. A whole document is never simply "for" or "against" because one document can support one claim and weaken another.
- Citations are product objects, not prose decoration.
- Retrieval and reasoning are separate stages. Retrieval builds sealed evidence packs; reasoning may only use those packs.
- Adverse authority is mandatory. Strategy output is incomplete unless it actively searches for and explains evidence against the client position.
- Human review is part of the system design. Lawyer approval, rejection, and requested changes must be persisted and auditable.
- Data quality is visible. OCR, translation, missing text, weak anchors, and source reliability warnings must affect confidence and display.

## Production Capabilities

### 1. Matter Intake and Case Positioning

- Structure raw user facts into parties, timeline, material facts, disputed facts, issues, missing facts, ambiguities, and contradictions.
- Capture the client position explicitly before stance classification.
- Mark position uncertainty when the user has not made the client side clear.
- Generate retrieval queries per issue, not only one general matter query.
- Persist structured case inputs with source spans and audit events.

### 2. Evidence Retrieval and Pack Sealing

- Retrieve with exact citation/provision lookup, BM25, phrase/fuzzy search, dense vector search, and reranking.
- Retrieve both supportive and adverse candidates through paired queries:
  - supporting authority queries
  - limitation or exception queries
  - contrary precedent queries
  - burden/procedure/jurisdiction risk queries
- Seal every research pack with schema version, token count, pack hash, retrieval trace, scoring breakdown, source warnings, and page anchors.
- Keep parent and child pack lineage for expanded searches.
- Preserve source ordering, rank, and query path so reviewers can inspect why an item appeared.

### 3. Claim-Level For/Against Analysis

- Introduce claim-level evidence assessments with stance values:
  - `supports_claim`
  - `contradicts_claim`
  - `mixed`
  - `context`
- Store assessment rationale, confidence score, risk level, source quote, page range, pack item ID, and review status.
- Allow one pack item to support one claim and contradict another.
- Group strategy output by claim, issue, and stance.
- Require explanation when evidence is classified as mixed.

### 4. Reasoning Pack and Preliminary Opinion Workflow

- Adopt the hybrid Phase 4 workflow from `/Users/imeshekanayake/Downloads/detailed.md` as the product reasoning specification:
  - Retrieval Pack
  - Authority Verification
  - Issue Matrix
  - Legal Element Matrix
  - Fact-to-Law Mapping
  - For/Against Brief
  - Missing Evidence Checklist
  - Preliminary Legal Opinion
  - Lawyer Review Pack
- Generate a production-grade lawyer-review reasoning pack with:
  - authority verification status
  - issue framing
  - legal element matrix
  - fact-to-law mapping
  - facts relied on and facts against each element
  - arguments for the client
  - adverse material
  - counterarguments
  - rebuttals
  - evidence strength ranking
  - missing evidence and missing authorities
  - preliminary opinion sections
  - lawyer review questions
  - citation and source-quality warnings
- Reject reasoning output when legal claim sentences lack citations.
- Reject reasoning output when cited pack item IDs are outside the sealed pack.
- Reject outcome-guarantee wording and require cautious preliminary language.
- Persist drafts, claims, counterarguments, risk rankings, structured reasoning metadata, and review items without applying a database migration.

### 5. Review, Audit, and Governance

- Add lawyer review queues for drafts, claims, adverse evidence, and mixed evidence.
- Persist reviewer decisions, comments, reviewer identity, timestamps, and before/after state.
- Provide case-scoped audit event views and organization audit views.
- Require signed authentication for case, pack, source, review, and audit endpoints.
- Add policy controls for source reliability, legal advice boundaries, prompt injection, and hidden-knowledge prevention.

### 6. UI and Case Workspace

- Add a reasoning pack and preliminary opinion first view for V2 matters.
- Add an evidence stance panel grouped by issue and claim.
- Add support/adverse/mixed/context badges derived from claim-level evidence assessments.
- Add source viewer links from every cited claim and adverse item.
- Add reviewer actions directly beside draft sections and evidence groups.
- Keep document-level labels as summaries only, never as the canonical classification.

### 7. Data and Corpus Readiness

- Maintain the current data folder structure outside Git until a data hosting plan is finalized.
- Publish corpus manifests, checksums, and acquisition metadata separately from raw assets.
- Track missing source coverage, OCR confidence, translation status, and searchability health.
- Keep licensed and public-domain corpora clearly separated.
- Add reproducible data hydration scripts for future environments.

## Milestones

### Phase 1: V2 Baseline Hardening

Outcome: V2 has production documentation, detached test execution, and a clear codebase map.

Deliverables:

- Production product roadmap.
- Engineering and testing playbook.
- Codebase map.
- Detached quality gate runner.
- GitHub V2 documentation sync.

Exit criteria:

- New docs exist in V2.
- Long quality checks can run in their own process with PID and log files.
- No production roadmap item depends on changing V1.

### Phase 2: Evidence Assessment Domain Model

Outcome: stance classification becomes a first-class domain contract.

Deliverables:

- Pydantic models for claim evidence assessment.
- Repository methods for storing and listing evidence assessments.
- API contracts for grouped support/adverse/mixed/context evidence.
- Migration plan for database changes, reviewed before execution.
- Tests for one evidence item serving different stances across different claims.

Exit criteria:

- Unit tests cover stance validation and citation-role mapping.
- Repository tests cover persistence and round-trip retrieval.
- Existing V1-style supported claims continue to pass.

### Phase 3: Adverse Retrieval Pipeline

Outcome: retrieval intentionally finds evidence against the client position.

Deliverables:

- Query expansion for supportive, adverse, limitation, exception, and procedural-risk searches.
- Retrieval trace metadata that records query intent.
- Reranking features that score source authority, recency, exactness, and adverse relevance.
- Evaluation fixtures for known supportive and adverse authorities.

Exit criteria:

- Retrieval evaluation measures supportive recall and adverse recall separately.
- Blind evaluation cases include at least one adverse authority per legal domain where available.
- Search results preserve exact citations and page anchors.

### Phase 4: Reasoning Pack and Preliminary Opinion Workflow

Outcome: V2 outputs a lawyer-review reasoning pack that converts retrieval evidence into an issue matrix, legal element matrix, fact-to-law mapping, for/against brief, missing evidence checklist, preliminary legal opinion, and lawyer review pack.

Deliverables:

- Roadmap update formally adopting the hybrid workstream from `detailed.md`.
- Structured reasoning-pack response schema.
- Authority verification, issue matrix, legal element, fact-to-law, for/against, missing evidence, preliminary opinion, and lawyer review models.
- Updated strategy prompts for `for_against_brief`, `preliminary_legal_opinion`, and `lawyer_review_pack`.
- Persistence of structured reasoning output in existing draft metadata.
- Human-readable reasoning pack stored as draft markdown.
- Review queue items for the draft, adverse reasoning, and missing evidence.

Exit criteria:

- Out-of-pack support, adverse, and mixed citations are rejected.
- Uncited legal conclusions are rejected.
- Outcome-guarantee wording is rejected.
- Unverified legal propositions are marked `requires_lawyer_verification`.
- Missing evidence is listed when facts, documents, case law, procedure, or authority verification are incomplete.
- Draft detail API returns structured reasoning metadata and review status.

### Phase 5: Production UI

Outcome: lawyers can inspect and review V2 evidence in the workspace.

Deliverables:

- Reasoning pack and preliminary opinion first view.
- Evidence stance panel.
- Claim detail with grouped citations.
- Source viewer deep links from every evidence item.
- Review actions for draft sections and evidence assessments.
- Workspace snapshot exposes reasoning-pack draft metadata without a schema migration.
- Review decision actions use the existing signed backend endpoint and audit workflow.

Exit criteria:

- E2E tests cover strategy generation, evidence inspection, source viewing, and reviewer decision.
- UI tests cover empty, loading, error, mixed, and adverse evidence states.
- All labels are claim-relative and do not imply document-level certainty.
- Reasoning-pack citation buttons navigate back to source pack evidence.
- Drafts without reasoning metadata remain readable as draft previews.

### Phase 6: Production Operations

Outcome: the service is observable, load-tested, and deployable.

Deliverables:

- Load-test scenarios for workspace snapshot, retrieval, strategy validation, source viewer, and review endpoints.
- Signed concurrent load runner with real-load and dry-run modes.
- Detached `load-plan` and `load` quality-gate modes with PID and log files.
- Metrics for latency, error rate, retrieval hit rate, adverse recall, pack size, token use, and citation validation failures.
- Runbooks for release flow, metrics review, data hydration, index rebuild, schema checks, rollback, incident response, and corpus quality audits.
- CI quality gate for backend, frontend, security, and contract tests.

Exit criteria:

- Load scenario contracts pass unit tests and dry-run validation.
- Real load tests meet agreed service-level targets on a production-like stack before deployment.
- E2E tests pass against a production-like local stack.
- Documentation covers setup, operation, testing, data handling, and release.

### Phase 7: Deployment Automation and Corpus Monitoring

Outcome: production deployment, hosted data operations, and recurring corpus/index monitoring are repeatable from a reviewed command manifest.

Deliverables:

- Manifest-driven release, deployment-readiness, hosted-data, and recurring-monitoring command plan.
- Operational plan renderer for JSON, shell, and Markdown evidence.
- Monitoring snapshot runner with plan mode and controlled execution mode.
- Hosted data strategy for object storage, manifests, digests, searchability audits, and no raw Git uploads.
- Release contract and runbook updates for deployment cutover readiness.

Exit criteria:

- Manifest contract tests pass.
- Operational plan renders release, deployment, hosted-data, and monitoring sections.
- Monitoring snapshot plan writes machine-readable evidence without requiring production services.
- Release docs separate local release evidence from production-like stack evidence.
- No V1 changes, no raw data upload, and no database schema migration.

### Phase 8: Deployment Readiness Evidence Pack

Outcome: deployment decisions are backed by a structured evidence pack that separates local release evidence from production-stack evidence.

Deliverables:

- Evidence requirements manifest for local release and production-stack readiness.
- Readiness pack builder that evaluates detached logs, JSON status reports, load reports, and searchability audits.
- Deployment decision states for ready, blocked, and missing production evidence.
- Detached readiness-pack gate mode.
- Contract, runbook, and release documentation for evidence collection.

Exit criteria:

- Evidence manifest contract tests pass.
- Local release evidence pack returns `ready` after detached Phase 8 gates pass.
- Production evidence pack identifies missing production-stack reports until real service evidence is attached.
- Release notes record local evidence and production deployment requirements separately.
- No V1 changes, no raw data upload, and no database schema migration.

### Phase 9: Release Artifact Bundle

Outcome: release evidence can be checksummed, bundled, and attached to GitHub releases without committing logs or raw data.

Deliverables:

- Release artifact manifest for approved local and production-stack evidence.
- Artifact report builder with SHA-256 checksums and missing-evidence classification.
- Optional tarball generation for release attachments.
- Detached artifact-report gate modes for local and production evidence.
- Contract, runbook, and release documentation for evidence artifact handling.

Exit criteria:

- Artifact manifest and packager tests pass.
- Local artifact report is complete after required local release docs/manifests exist.
- Production artifact report records missing production-stack files until real evidence exists.
- Bundle excludes raw corpus data and normal runtime directories.
- No V1 changes, no raw data upload, and no database schema migration.

### Phase 10: Release Asset Publication Workflow

Outcome: approved evidence bundles can be safely planned for GitHub release upload with explicit execution controls.

Deliverables:

- Publication manifest for approved release assets.
- Publication plan builder that verifies asset existence, allowed paths, sizes, and SHA-256 digests.
- GitHub release upload script with plan mode by default and explicit `--execute` for mutation.
- Detached asset-publication-plan gate.
- Contract, runbook, and release documentation for release asset publication.

Exit criteria:

- Publication manifest and plan tests pass.
- Publication plan is `ready` only for approved release-artifact paths.
- Raw data, `.env`, `node_modules`, `.next`, and Git internals are blocked from publication.
- Actual GitHub asset upload remains explicit and auditable.
- No V1 changes, no raw data upload, and no database schema migration.

### Phase 11: Published Asset Verification

Outcome: published GitHub release assets are independently verified against the approved local asset checksums and sizes.

Deliverables:

- Remote release asset verification script.
- GitHub asset digest and size comparison against approved local release artifact files.
- Deterministic release bundle generation so unchanged evidence rebuilds keep stable checksums.
- Detached asset-verification gate.
- Verification report with `verified`, `missing_remote`, and `mismatch` states.
- Contract, runbook, and release documentation for post-publication provenance.

Exit criteria:

- Verification tests pass for match, mismatch, and saved remote asset payloads.
- Published Phase 9 assets verify against local SHA-256 digests.
- Verification report is generated without committing logs or bundles.
- No V1 changes, no raw data upload, and no database schema migration.

### Phase 12: Release Provenance Ledger

Outcome: each completed phase can be represented as a machine-readable provenance ledger tying the GitHub release, tag commit, release docs, validation logs, and verification reports into one auditable record.

Deliverables:

- Release provenance manifest for the latest completed phase.
- Provenance ledger builder for GitHub release metadata, tag commit verification, required docs, detached logs, and JSON status reports.
- Detached release-provenance gate.
- Ledger statuses for verified, failed, and missing provenance evidence.
- Contract, runbook, and release documentation for release audit provenance.

Exit criteria:

- Provenance tests pass for verified evidence, missing evidence, draft releases, and saved metadata payloads.
- Live provenance ledger verifies the Phase 11 GitHub release and remote tag commit.
- Required Phase 11 evidence docs, detached logs, and asset verification report are checksummed.
- Provenance ledger is generated without committing logs or release bundles.
- No V1 changes, no raw data upload, and no database schema migration.

### Phase 13: Release Attestation Envelope

Outcome: each completed release can produce a deterministic attestation envelope that binds the release tag, release URL, tag commit, provenance ledger, and release documentation into a stable checksum-backed statement.

Deliverables:

- Release attestation manifest for the latest completed phase.
- In-toto-style attestation statement with subject digests and release predicate metadata.
- Deterministic canonical SHA-256 attestation digest.
- Detached release-attestation gate.
- Contract, runbook, and release documentation for checksum-backed attestations.

Exit criteria:

- Attestation tests pass for verified subjects, deterministic digest generation, failed provenance status, and saved metadata payloads.
- Live attestation verifies the Phase 12 GitHub release and remote tag commit.
- Required Phase 12 provenance ledger, release docs, and provenance manifest are checksummed as subjects.
- Attestation envelope is generated without committing logs or release bundles.
- No V1 changes, no raw data upload, and no database schema migration.

### Phase 14: Release Signing Readiness Gate

Outcome: release signing is governed by an explicit readiness gate that verifies the prior release, required attestation evidence, approved signing modes, and absence of forbidden private-key files before any signing workflow can be considered.

Deliverables:

- Release signing readiness manifest for the latest completed phase.
- Signing readiness report for release metadata, tag commit identity, attestation evidence, approved signing modes, and forbidden secret-file scans.
- Detached signing-readiness gate.
- Explicit disabled-by-default signing execution policy.
- Contract, runbook, and release documentation for future keyless or KMS/HSM signing.

Exit criteria:

- Signing readiness tests pass for ready reports, forbidden key files, unsupported signing modes, and saved metadata payloads.
- Live signing readiness verifies the Phase 13 GitHub release and remote tag commit.
- Required Phase 13 attestation envelope, release docs, and attestation manifest are checksummed.
- Signing execution remains disabled unless a reviewed approval flag and environment plan are supplied.
- No V1 changes, no raw data upload, no private signing keys, and no database schema migration.

### Phase 15: Release Signing Execution Plan

Outcome: approved signing commands can be generated as a deterministic non-mutating plan, with release/tag verification, readiness evidence checks, artifact checksums, expected signature outputs, and verification commands captured before any signing execution is permitted.

Deliverables:

- Release signing plan manifest for the latest completed phase.
- Signing plan report for release metadata, tag commit identity, readiness report status, signing artifacts, planned commands, and expected outputs.
- Detached signing-plan gate.
- Sigstore keyless and KMS/HSM command templates.
- Contract, runbook, and release documentation for controlled signing execution planning.

Exit criteria:

- Signing plan tests pass for planned reports, missing artifacts, unready readiness reports, and saved metadata payloads.
- Live signing plan verifies the Phase 14 GitHub release and remote tag commit.
- Required Phase 13 attestation and Phase 14 signing readiness artifacts are checksummed.
- Signing commands are planned but not executed unless a future reviewed approval flag is supplied.
- No V1 changes, no raw data upload, no private signing keys, no signature output files, and no database schema migration.

## Phase 8 Production Evidence Requirements

Before a production cutover, attach passing evidence for:

- schema check
- rollback-only schema smoke
- RAG health with search indexes
- Postgres/OpenSearch/Qdrant index consistency
- real signed load suite
- full corpus searchability audit

## Production Readiness Gates

Every release candidate must pass:

- Unit tests for models, validators, policy checks, prompt builders, and utility functions.
- Integration tests for repositories, API endpoints, auth, research packs, source anchors, and review flows.
- Retrieval evaluation for supportive and adverse evidence.
- End-to-end tests for the lawyer workflow.
- Load tests for retrieval and source-viewer paths.
- Secret scan.
- Schema check and rollback-only schema smoke test.
- Frontend lint, unit tests, build, and dependency audit.
- Documentation review for user-facing, engineering, and operations docs.

## Initial Service-Level Targets

- Research pack API p95 latency below 8 seconds for warm indexes and bounded result sizes.
- Source viewer p95 latency below 1.5 seconds when pages and anchors exist.
- Strategy validation p95 latency below 1 second.
- Review queue p95 latency below 750 ms.
- Citation validation failure rate visible as a metric.
- Zero known uncited legal claims in persisted strategy drafts.
- Zero known out-of-pack citations in persisted strategy drafts.

## Documentation Deliverables

- Product roadmap.
- Engineering and testing playbook.
- Codebase map.
- API contract documentation.
- Data layout and data hosting plan.
- Database schema change plan.
- Retrieval evaluation guide.
- Load testing guide.
- Release checklist.
- Operations runbook.
- Security and privacy review notes.

## Non-Negotiable Constraints

- V1 remains untouched except for explicitly approved sync or archival work.
- V2 work stays in `V2-For-Against-Docs`.
- Database schema changes require a separate reviewed migration plan before execution.
- Large corpus data is not committed to normal Git.
- Long-running tests and quality gates must run detached with PID and log files.
- Phase 4 must not apply a database migration; structured reasoning output is stored in existing draft metadata until a reviewed schema migration is approved.
- Phase 6 must not treat a dry-run load plan as production-like load evidence.
- Phase 7 must not execute hosted-data mutation commands unless `--execute` and production environment variables are deliberately supplied.
- Phase 8 must not mark production deployment ready when production-stack evidence is missing or failed.
- Phase 9 must not commit release artifact tarballs, logs, or raw evidence outputs to normal Git.
- Phase 10 must not upload release assets unless `--execute` is deliberately supplied.
- Phase 11 must fail verification when GitHub asset digests or sizes do not match local approved artifacts.
- Phase 12 must fail provenance verification when release metadata, tag commits, required docs, detached logs, or JSON evidence statuses are missing or mismatched.
- Phase 13 must fail attestation generation when release metadata, tag commits, provenance ledger status, or required subject digests are missing or mismatched.
- Phase 14 must fail signing readiness when release metadata, tag commits, required attestation evidence, approved signing modes, or forbidden private-key file scans fail.
- Phase 15 must fail signing planning when release metadata, tag commits, readiness reports, or required signing artifacts are missing or mismatched.
