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
- Agentic legal research must be tool-routed and auditable. The system may plan, clarify, retrieve, expand, verify, and draft, but every step must be recorded as a bounded tool action with source boundaries and reviewer-facing rationale.
- Wider authority expansion produces candidates, not legal citations, until those authorities are promoted into a sealed reviewed pack.
- Clarification is a safety feature. Missing material facts, jurisdiction, dates, parties, relief, case numbers, registration numbers, or client position must trigger clarification or cautious missing-evidence treatment instead of confident conclusions.
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

### 8. Agentic Tool Routing and Matter Memory

- Add a schema-constrained research agent that can route between intake structuring, database search, authority expansion, official-source verification, clarification, answer drafting, and lawyer-review-pack generation.
- Keep database-first retrieval as the default. Official-source checks are used only when the sealed corpus is incomplete, current-law verification is required, or candidate authority metadata is uncertain.
- Persist a tool trace for every routed step with purpose, input summary, source boundary, result count or status, selected outputs, and reviewer-facing note.
- Maintain matter/session memory for client facts, selected authorities, retrieved packs, candidate expansion authorities, adverse material, missing-evidence tasks, and prior lawyer review decisions.
- Separate promoted sealed authorities from unverified candidate authorities in all outputs.
- Add expert-style evaluation rubrics for legal taxonomy, legal logic, authority quality, citation precision, adverse reasoning, missing-evidence coverage, and lawyer-review readiness.

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

### Phase 16: Maat-Informed Agentic Research Workflow Plan

Outcome: the V2 roadmap formally adopts the relevant lessons from the Maat legal agent paper as a production plan: tool routing, matter memory, clarification, database-first retrieval, authority expansion, official-source verification, and expert evaluation. The paper informs the workflow design, while V2's sealed-pack, citation-validation, lawyer-review, and release-discipline rules remain authoritative.

Product specification source:

- Maat paper: `https://arxiv.org/pdf/2605.27331v1`
- Existing Phase 4 reasoning-pack specification: `/Users/imeshekanayake/Downloads/detailed.md`
- Existing V2 production roadmap, release discipline, citation safety rules, and no-final-legal-advice boundary.

Implementation plan:

- Add an agent router contract with these bounded tools:
  - `case_intake_structurer`
  - `search_database`
  - `expand_authorities`
  - `official_source_check`
  - `ask_clarification`
  - `answer_from_pack`
  - `lawyer_review_pack`
- Add tool-trace schemas and validators without applying a database migration. Store traces in existing metadata fields until a reviewed schema plan is approved.
- Add matter/session memory structures for selected authorities, retrieved packs, stage-1 authority candidates, client facts, adverse material, unresolved missing-evidence tasks, and lawyer review state.
- Add a clarification policy for missing client position, parties, jurisdiction, dates, relief sought, registration numbers, case numbers, procedural posture, and material disputed facts.
- Add an authority-promotion workflow so wider-search candidates remain non-citable until retrieved, anchored, verified, and sealed into a reviewed pack.
- Add official-source fallback checks for current-law and authority-verification gaps, preferring primary or official sources and marking verification status.
- Add expert-style offline evaluation reports for legal logic, taxonomy, issue spotting, authority quality, citation precision, missing evidence, adverse reasoning, and lawyer-review readiness.

Exit criteria:

- Router unit tests pass for database-first search, clarification, authority expansion, official-source fallback, and answer-from-pack paths.
- Every tool call emits trace metadata with purpose, input summary, source boundary, result count or status, selected outputs, and reviewer-facing note.
- Clarification triggers prevent stronger preliminary opinions when material facts are absent.
- Authority expansion candidates are never cited as law until promoted into the sealed pack.
- Official-source checks mark authorities as `verified`, `partially_verified`, or `requires_lawyer_verification`.
- Expert-evaluation output passes on at least one tuned scenario and identifies deliberate adversarial failures.
- No V1 changes, no raw data upload, and no database migration.

### Phase 17: Full Tuned-Scenario Agentic Validation

Outcome: the Maat-informed workflow is validated across the existing 10 tuned scenarios before backend persistence or UI expansion. The goal is to prove that long-text, multi-document reasoning produces useful lawyer-review packs with strong supportive arguments, adverse arguments, missing-evidence tasks, authority candidates, and cautious preliminary opinions.

Deliverables:

- Detached validation run for all 10 tuned scenarios.
- Per-scenario reports covering:
  - base sealed pack contents
  - supportive evidence retrieval
  - adverse evidence retrieval
  - wider authority candidates
  - promoted versus unpromoted authorities
  - issue matrix
  - legal element matrix
  - fact-to-law mapping
  - for/against brief
  - missing evidence checklist
  - preliminary opinion
  - lawyer-review readiness
- Failure ledger for weak retrieval, missing authority names, unclear case names, uncited propositions, overconfident language, and missing adverse analysis.
- Domain templates for recurring Sri Lankan legal areas, starting with intellectual property, industrial disputes, administrative law, contract, land, and civil procedure.

Exit criteria:

- All 10 tuned scenarios complete without runtime errors.
- Every scenario separates facts, law, application, supportive arguments, adverse arguments, missing evidence, review items, and next retrieval tasks.
- No out-of-pack citations appear in final legal reasoning.
- Candidate authorities are traceable and clearly marked until promoted.
- Missing-evidence entries cover facts, client documents, procedure, authorities, and verification gaps.
- Preliminary opinions use cautious lawyer-review language and never present final legal advice.
- Release notes and evidence summaries are produced without raw data upload, database mutation, or V1 changes.

### Phase 18: Backend Workflow Integration for Agentic Research

Outcome: the validated agentic workflow becomes a backend V2 workflow that can generate and persist lawyer-review packs through existing APIs and metadata storage, still without a schema migration unless a separate migration plan is approved.

Deliverables:

- Backend service layer for routed research steps.
- API contracts for starting a routed research run, inspecting tool traces, requesting clarification, approving authority promotion, and generating a lawyer-review pack.
- Draft metadata persistence for reasoning packs, tool traces, candidate authority state, clarification state, and expert-evaluation summaries.
- Review queue integration for draft review, adverse-material review, authority-promotion review, and missing-evidence review.
- Integration tests for happy path, clarification-required path, candidate-authority path, official-source verification path, and rejection of unsafe output.

Exit criteria:

- Backend integration tests prove full reasoning-pack persistence and retrieval.
- Draft detail returns structured reasoning metadata, tool traces, and candidate authority state.
- Review queue includes draft, adverse, authority-promotion, and missing-evidence items.
- Citation validators reject out-of-pack citations and uncited legal conclusions.
- No database migration is applied unless separately reviewed and approved.

### Phase 19: Agentic Workspace Visibility

Outcome: Phase 18 agentic metadata is visible in the lawyer workspace without changing the database schema.

Deliverables:

- Workspace draft summaries expose `agenticResearchPlan` and `matterMemory`.
- Reasoning tab renders tool routes, clarification needs, authority candidates, matter memory, and sealed-pack boundaries.
- TypeScript contracts cover tool traces, authority candidates, clarification needs, agentic plans, and matter memory.
- Backend snapshot coverage confirms agentic metadata is read from existing draft metadata.
- UI rendering coverage confirms candidate authorities remain visually separate from citable sealed-pack items.

Exit criteria:

- Agentic metadata appears in workspace draft summaries.
- Clarification blockers are visible before preliminary opinions.
- Tool traces show source boundary and status.
- Candidate authorities are not shown as citable unless later promoted.
- Frontend lint, component tests, backend metadata tests, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or final legal advice generation.

### Phase 20: Agentic Review Queue Actions

Outcome: agentic workflow metadata becomes actionable through existing review queue decisions while promotion and clarification-answering remain separate workflows.

Deliverables:

- `clarification_need` review items for unresolved blocking clarifications.
- `authority_candidate` review items for non-citable authority candidates.
- Existing review decision endpoint accepts the new review item types.
- Audit events are written for the new review decisions.
- Review queue UI and fixtures cover the new item types.
- Contract documents the boundary that review decisions do not promote candidates or answer clarifications.

Exit criteria:

- Blocking clarification needs create high-priority review items.
- Authority candidates create high-priority review items.
- Review decisions work and are audited for both new item types.
- Draft status is not mutated by clarification or authority-candidate decisions.
- Candidate authorities remain non-citable and unpromoted.
- Existing draft, claim, adverse, and missing-evidence review behavior remains green.
- No V1 changes, raw data upload, database migration, official-source web execution, or final legal advice generation.

### Phase 21: Authority Pack Expansion Planning

Outcome: approved authority-candidate reviews produce explicit pack-expansion plans that can be executed in a later phase, while candidate authorities remain non-citable until retrieved, anchored, verified, and sealed.

Deliverables:

- `authority_pack_expansion_plan.v1` structured metadata.
- Official-source expansion requests derived from approved authority candidates.
- Draft metadata persistence without a database migration.
- Audit metadata showing the generated expansion plan.
- Workspace visibility for planned expansion queries.

Exit criteria:

- Authority-candidate approval creates a draft-scoped expansion plan.
- Expansion requests require official-source retrieval and use `authority_candidate_pack_expansion`.
- Candidate authority status is not promoted by approval.
- Draft detail and workspace snapshot expose the plan.
- Tests cover model validation, builder behavior, repository persistence, audit metadata, and UI display.

### Phase 22: Authority Pack Expansion Execution

Outcome: a planned authority pack-expansion request can be executed through the existing research-pack expansion API, producing a child pack while preserving the non-citable candidate boundary.

Deliverables:

- Execution endpoint for a selected authority expansion request.
- Child pack persistence through the existing research-pack expansion path.
- Draft metadata execution records with child pack ID, pack hash, item count, user, timestamp, and request hash.
- Audit event for expansion execution.
- Workspace-safe visibility of executed child pack IDs.

Exit criteria:

- Executing a request creates and stores a parent-linked child research pack.
- Duplicate execution of the same request index is rejected.
- Plan status reflects `partially_executed` or `executed`.
- Candidate authorities remain non-citable and unpromoted.
- Tests cover endpoint behavior, repository metadata updates, schema validation, and UI type/display safety.

### Phase 23: Authority Expansion Idempotency and Locking

Outcome: authority expansion execution metadata is protected against concurrent duplicate writes.

Deliverables:

- Locked draft-row metadata read for execution recording.
- API duplicate re-check under lock before execution metadata is written.
- `409 Conflict` behavior for duplicate request execution.
- Review-documented boundary for remaining pre-retrieval reservation work.

Exit criteria:

- Execution-record duplicate checks and metadata append occur while the draft row is locked.
- API duplicate re-check uses the locked path.
- Existing successful execution behavior remains green.
- Duplicate execution conflict tests pass.
- Candidate authorities remain non-citable and unpromoted.

### Phase 24: Authority Expansion Reservation

Outcome: planned authority expansion requests are reserved before retrieval so duplicate actions cannot create duplicate child packs.

Deliverables:

- `authority_pack_expansion_reservation.v1` metadata records.
- Locked reservation creation before research-pack expansion.
- Reservation completion after execution metadata is written.
- Reservation failure metadata for retry-safe retrieval failures.
- Duplicate reservation conflict handling before retrieval begins.

Exit criteria:

- Duplicate request execution returns `409 Conflict` before retrieval.
- Successful execution marks the reservation `completed`.
- Retrieval failure marks the reservation `failed` and permits a future retry.
- Existing execution records and audit events remain green.
- Candidate authorities remain non-citable and unpromoted.

### Phase 25: Child Pack Source Anchoring and Authority Verification

Outcome: executed authority expansion child packs are inspected against source anchors before any authority can be promoted or cited.

Deliverables:

- `authority_pack_verification.v1` metadata records on authority expansion plans.
- Per-item verification records for source anchors, citation metadata, authority level, and lawyer-review issues.
- Locked verification writes against draft metadata.
- API endpoint to verify an executed child pack.
- Workspace display of verified/needs-review authority child packs.

Exit criteria:

- Verification only accepts child packs already recorded by the execution phase.
- Child pack hashes must match the execution record before verification is written.
- Verified authority items require a source anchor and citation.
- Weak, missing, or unanchored items are marked `requires_lawyer_review`.
- Candidate authorities remain non-citable and unpromoted.
- No V1 changes, raw data upload, or database migration.

### Phase 26: Controlled Authority Promotion

Outcome: verified authority expansion child-pack items can be promoted into citable matter-memory authority references under lawyer-controlled approval.

Deliverables:

- `authority_pack_promotion.v1` metadata records on authority expansion plans.
- Promotion API endpoint for verified child packs.
- Promotion validators that require executed, verified, anchored pack items.
- Matter-memory updates for `promoted_to_sealed_pack` authority candidates.
- Workspace display of promoted authority item counts and citable state.

Exit criteria:

- Promotion rejects unverified, partially verified, unanchored, or unknown pack items.
- Promotion records are citable only when backed by verified child-pack items.
- Candidate authorities receive `promoted_pack_item_ids` only after promotion.
- Matter memory records the child pack as sealed and citable.
- Duplicate promotion attempts are rejected.
- No V1 changes, raw data upload, or database migration.

### Phase 27: Full 10-Case Verification and Promotion Validation

Outcome: the tuned 10-case validation set is run through retrieval, lawyer-review pack generation, missing-evidence checks, and authority promotion readiness scoring.

Deliverables:

- Phase 27 aggregate validation runner for the full tuned case set.
- Official Gazette promotion-readiness fix so Gazettes are not incorrectly blocked as weak authorities.
- Full 10-case retrieval report using 25 documents per case.
- Full 10-case lawyer-review readiness summary.
- Validation evidence showing supportive/adverse reasoning, missing evidence, and promotion-eligible authority coverage.

Exit criteria:

- All 10 tuned cases complete without runtime errors.
- Retrieval stage reports `10/10` passing cases.
- Lawyer-review readiness scorer reports `10/10` ready cases.
- Each case has for/against reasoning and missing-evidence coverage.
- Promotion eligibility includes Acts, Supreme Court/Court of Appeal/law-report authorities, and official Gazettes where applicable.
- No V1 changes, raw data upload, or database migration.

### Phase 28: Authority Workflow UI Integration

Outcome: the lawyer workspace can drive the existing authority expansion, verification, and promotion backend workflow from the reasoning panel.

Deliverables:

- Server actions and signed API clients for authority expansion execution, child-pack verification, and controlled promotion.
- Reasoning panel action controls for `Execute`, `Verify`, and `Promote`.
- Workspace state refresh after each authority workflow action.
- Inline display of child-pack IDs, verification item status, promoted authority items, and citable boundaries.
- UI tests for the full Execute -> Verify -> Promote path.

Exit criteria:

- The UI calls the existing backend endpoints with case, draft, plan, request, child-pack, and pack-item identifiers.
- Verified child-pack items remain non-citable until controlled promotion succeeds.
- Promotion sends only verified, non-review pack item IDs.
- Lawyer-facing status separates planned, executed, verified, promoted, citable, and not-citable states.
- Detached backend tests and frontend quality gate pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 29: Browser Workflow Validation Evidence

Outcome: the authority workflow UI is validated in a real browser against a representative matter without touching the shared database.

Deliverables:

- Browser workflow validation runner using the real Next workspace and a temporary signed local backend.
- Representative case fixture covering reasoning pack, authority expansion plan, executed child pack, verification record, and promotion record.
- Chrome-driven Execute -> Verify -> Promote validation.
- Local screenshot, JSON report, Markdown summary, and Next dev log evidence under `logs/phase29-browser-workflow`.
- Detached quality-gate mode for repeatable browser workflow validation.

Exit criteria:

- Browser renders the representative matter and reasoning panel.
- Browser completes Execute -> Verify -> Promote through the real UI controls.
- Fake backend observes signed workspace, execute, verify, and promote API calls.
- Promotion sends only the verified pack item ID.
- No React hydration mismatch is observed with browser extensions disabled.
- Detached backend tests, frontend quality gate, and Phase 29 browser workflow validation pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 30: UI Deployment Readiness

Outcome: the validated authority workflow UI has a repeatable deployment-readiness gate before any hosted staging or production cutover.

Deliverables:

- Machine-readable readiness manifest for UI deployment evidence and hosted environment requirements.
- Readiness report builder that produces `ready_for_hosted_env_review`, `ready_for_deployment_review`, or `blocked`.
- Detached local readiness gate that verifies Phase 29 browser evidence and workflow wiring.
- Optional hosted environment gate that checks required variables without printing secret values.
- Staging/production guard that blocks development-only `SL_LEGAL_UI_USER_ID`.
- Operator runbook for local readiness and hosted environment review.

Exit criteria:

- Phase 29 browser workflow evidence is present and passing.
- `phase29:e2e` and `phase29-browser-workflow` remain wired.
- Required UI environment variables are documented in `.env.example`.
- Hosted environment checks do not expose secret values.
- Detached backend tests, frontend quality gate, Phase 30 readiness gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 31: Staging Cutover Dry Run

Outcome: the UI deployment readiness gate is converted into a staging cutover dry-run plan with explicit smoke commands, hosted environment boundary, approvals, and rollback steps.

Deliverables:

- Machine-readable staging cutover dry-run manifest.
- Dry-run report builder that produces `ready_for_hosted_env_setup`, `ready_for_staging_cutover`, or `blocked`.
- Detached `staging-cutover-dry-run` mode.
- Smoke-test plan for hosted env readiness, browser workflow, backend tests, and frontend quality.
- Manual approval and rollback checklist for staging cutover.
- Operator runbook for local and hosted staging execution.

Exit criteria:

- Phase 30 readiness report is present and accepted.
- Local dry run returns `ready_for_hosted_env_setup`.
- Hosted staging can return `ready_for_staging_cutover` only after environment inspection passes.
- Smoke commands and expected evidence paths are emitted without secret values.
- Detached backend tests, frontend quality gate, Phase 31 dry run, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 32: Hosted Staging Execution Pack

Outcome: the staging cutover dry run becomes an executable hosted-staging checklist with private reviewer session-token support and rollback controls.

Deliverables:

- Machine-readable hosted staging execution manifest.
- Execution-pack report builder that produces `ready_for_hosted_configuration`, `ready_for_hosted_staging_execution`, or `blocked`.
- Detached `hosted-staging-execution-pack` mode.
- Private signed UI session token utility for lawyer-review staging sessions.
- Hosted staging runbook covering env setup, token handling, smoke checks, and rollback.

Exit criteria:

- Phase 31 dry-run report is present and accepted.
- Local execution pack returns `ready_for_hosted_configuration`.
- Hosted execution pack can return `ready_for_hosted_staging_execution` only after Phase 31 is `ready_for_staging_cutover`.
- Session-token utility is tested and does not write tokens into Git-tracked files.
- Detached backend tests, frontend quality gate, Phase 32 execution-pack gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 33: Hosted Staging Execution Validation

Outcome: hosted staging execution evidence is validated by a repeatable gate that distinguishes local pending state from real hosted-staging completion.

Deliverables:

- Machine-readable hosted staging validation manifest.
- Validation report builder that produces `awaiting_hosted_execution`, `hosted_staging_validated`, or `blocked`.
- Detached `hosted-staging-validation` mode.
- Required hosted evidence list covering Phase 30 env readiness, Phase 31 cutover, Phase 32 execution pack, browser smoke, backend tests, frontend quality, operator review, and lawyer-owner acceptance.
- Operator runbook for attaching hosted staging evidence without committing secrets or tokens.

Exit criteria:

- Phase 32 prerequisites are present and accepted.
- Local validation returns `awaiting_hosted_execution`.
- Real hosted validation can return `hosted_staging_validated` only after all hosted evidence passes.
- Failed hosted evidence blocks production planning.
- Detached backend tests, frontend quality gate, Phase 33 validation gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 34: Real Backend and DB Staging Validation

Outcome: hosted staging proves that V2 is running against the real backend and a controlled read-only staging DB path before production cutover planning continues.

Deliverables:

- Machine-readable backend DB staging validation manifest.
- Validation report builder that produces `awaiting_backend_db_staging_evidence`, `backend_db_staging_validated`, or `blocked`.
- Detached `backend-db-staging-validation` mode.
- Required evidence list covering Phase 33 validation, hosted API health, signed workspace API smoke, read-only DB health, zero-write DB audit, authority workflow, document source viewer, and operator DB acceptance.
- Operator runbook for attaching backend and DB staging evidence without committing secrets, raw data, DB URLs, or signed session material.

Exit criteria:

- Local validation returns `awaiting_backend_db_staging_evidence`.
- Hosted validation can return `backend_db_staging_validated` only after Phase 33 is validated and all backend/DB evidence passes.
- DB evidence proves `access_mode=read_only`, `write_count=0`, `migration_count=0`, and `raw_data_uploaded=false`.
- Failed backend evidence, nonzero writes, migration evidence, or raw data upload evidence blocks production planning.
- Detached backend tests, frontend quality gate, Phase 34 validation gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 35: Hosted Evidence Capture Plan

Outcome: the Phase 34 backend/DB staging evidence is converted into a repeatable hosted capture plan with environment validation, signed smoke-test boundaries, and DB write classification before any real hosted evidence is attached.

Deliverables:

- Machine-readable hosted evidence capture manifest.
- Capture-plan report builder that produces `ready_for_hosted_capture_configuration`, `ready_for_capture_execution`, or `blocked`.
- Detached `hosted-evidence-capture-plan` mode.
- Secret-safe environment gate for staging API base URL, staging user ID, case ID, document ID, auth signing secret, and operator DB confirmations.
- Capture task list for `/health`, signed workspace smoke, authority workflow smoke, document-source smoke, read-only DB evidence, DB write guard evidence, and operator DB acceptance.
- Write classification rules distinguishing read-only checks, allowed audit-event-only smoke checks, and prohibited domain writes.
- Operator runbook for gathering Phase 34 evidence under ignored `logs/` paths.

Exit criteria:

- Local validation returns `ready_for_hosted_capture_configuration`.
- Hosted environment validation can return `ready_for_capture_execution` only when required variables and operator confirmations are present.
- Any capture task that can write to the DB must declare an allowed write classification.
- The capture plan never prints secret values or writes Phase 34 evidence from local execution.
- Detached backend tests, frontend quality gate, Phase 35 capture-plan gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 36: Hosted Evidence Capture Runner

Outcome: the Phase 35 capture plan becomes an executable hosted runner that can gather Phase 34 evidence in staging, while local release validation remains dry-run and non-mutating.

Deliverables:

- Machine-readable hosted evidence capture runner manifest.
- Runner script that produces `ready_for_hosted_capture_runner_configuration`, `ready_for_hosted_capture_execution`, `hosted_evidence_captured`, or `blocked`.
- Detached `hosted-evidence-capture-runner` mode that runs dry by default.
- Explicit `--execute --include-environment` path for hosted staging capture.
- Signed GET smoke checks for workspace, authority workflow, and document-source status, with scrubbed logs only.
- Operator JSON generation for DB read-only health, DB write guard, and DB acceptance.
- Response-shape checks for hosted API and signed API smoke paths.

Exit criteria:

- Local runner validation returns `ready_for_hosted_capture_runner_configuration`.
- Hosted dry-run with environment can return `ready_for_hosted_capture_execution`.
- Hosted execution can return `hosted_evidence_captured` only after all capture tasks write scrubbed evidence successfully.
- Signed smoke logs do not contain secrets, signed cookies, DB URLs, raw document bodies, or raw data.
- Detached backend tests, frontend quality gate, Phase 36 runner gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 37: Hosted Capture Acceptance Gate

Outcome: hosted evidence captured by Phase 36 is accepted only after the captured files are complete, scrubbed, and Phase 34 validates the backend/DB staging evidence.

Deliverables:

- Machine-readable hosted capture acceptance manifest.
- Acceptance report builder that produces `awaiting_hosted_capture_execution`, `awaiting_captured_evidence_files`, `awaiting_phase34_backend_db_validation`, `hosted_capture_accepted`, or `blocked`.
- Detached `hosted-capture-acceptance` mode.
- Captured-evidence checks for API health, signed workspace smoke, authority workflow smoke, document-source smoke, read-only DB health, DB write guard, and operator DB acceptance.
- Forbidden-content scan for signing headers, session cookies, DB URLs, private keys, raw document bodies, and API key labels.
- Acceptance dependency on Phase 34 `backend_db_staging_validated` status.

Exit criteria:

- Local acceptance returns `awaiting_hosted_capture_execution`.
- Hosted acceptance can return `hosted_capture_accepted` only after Phase 36 reports `hosted_evidence_captured` and Phase 34 reports `backend_db_staging_validated`.
- Captured logs and JSON evidence contain no forbidden hosted-capture content.
- Failed or incomplete captured evidence blocks production planning.
- Detached backend tests, frontend quality gate, Phase 37 acceptance gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

### Phase 38: Hosted Capture Execution Orchestrator

Outcome: the hosted evidence path is executed through one guarded staging workflow that refreshes Phase 35, Phase 36, Phase 34, and Phase 37 readiness reports in sequence.

Deliverables:

- Machine-readable hosted capture execution manifest.
- Execution orchestrator that produces `awaiting_hosted_capture_configuration`, `ready_for_hosted_capture_execution`, `hosted_capture_executed_pending_backend_db_validation`, `hosted_capture_executed_pending_acceptance`, `hosted_capture_execution_accepted`, or `blocked`.
- Detached `hosted-capture-execution` mode that remains dry-run and non-mutating by default.
- Explicit `--execute --include-environment` path for real hosted staging capture.
- Chained refresh of Phase 35 environment preflight, Phase 36 capture runner, Phase 34 backend/DB validation, and Phase 37 capture acceptance.
- Operator runbook for hosted dry-run, hosted execution, and downstream status review.

Exit criteria:

- Local detached execution returns `awaiting_hosted_capture_configuration`.
- Hosted dry-run with environment returns `ready_for_hosted_capture_execution`.
- Hosted execution can advance only after Phase 36 reports `hosted_evidence_captured`.
- Accepted hosted execution requires Phase 34 `backend_db_staging_validated` and Phase 37 `hosted_capture_accepted`.
- Execution reports and captured evidence contain no secrets, signed headers, session cookies, DB URLs, raw document bodies, or raw data.
- Detached backend tests, frontend quality gate, Phase 38 execution gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.

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
