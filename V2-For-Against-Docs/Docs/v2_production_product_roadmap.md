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

Exit criteria:

- E2E tests cover strategy generation, evidence inspection, source viewing, and reviewer decision.
- UI tests cover empty, loading, error, mixed, and adverse evidence states.
- All labels are claim-relative and do not imply document-level certainty.

### Phase 6: Production Operations

Outcome: the service is observable, load-tested, and deployable.

Deliverables:

- Load-test scenarios for retrieval, strategy generation, source viewer, and review endpoints.
- Metrics for latency, error rate, retrieval hit rate, adverse recall, pack size, token use, and citation validation failures.
- Runbooks for data hydration, index rebuild, schema checks, rollback, incident response, and corpus quality audits.
- CI quality gate for backend, frontend, security, and contract tests.

Exit criteria:

- Load tests meet agreed service-level targets.
- E2E tests pass against a production-like local stack.
- Documentation covers setup, operation, testing, data handling, and release.

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
