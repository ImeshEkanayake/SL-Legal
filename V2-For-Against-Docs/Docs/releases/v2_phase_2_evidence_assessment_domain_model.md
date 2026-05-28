# V2 Phase 2 Release: Evidence Assessment Domain Model

## Release Goal

Phase 2 turns for-and-against evidence into a first-class, claim-level backend contract while preserving the shared database and V1-compatible supported claim workflow.

## Included

- Pydantic models for claim evidence assessment requests, grouped responses, stance groups, and persisted assessment items.
- Stance-to-citation-role mapping for support, adverse, mixed, and context evidence.
- Repository methods to create, persist, round-trip, and group evidence assessments using the existing database tables.
- Signed API endpoints for creating and listing grouped claim evidence assessments.
- Unit tests for stance validation and role mapping.
- API tests for grouped support/adverse contracts.
- Integration coverage for one pack item supporting one claim and contradicting another.
- Migration plan for a future dedicated `claim_evidence_assessments` table.

## Production Readiness Criteria

Phase 2 is releasable when:

- Unit tests cover stance validation, mixed-rationale validation, and citation-role mapping.
- Repository tests prove persistence and grouped round-trip retrieval.
- API tests prove signed create and grouped list contracts.
- Existing strategy draft and V1-style supported claims still pass.
- Secret scan and detached backend/frontend quality gates pass.
- No database migration is executed.
- No V1 code, data folder, or shared database content is changed.

## Validation Results

Local validation completed on 2026-05-28:

- Detached backend test run: `logs/test-runs/phase2-tests-final.log`
  - Result: `220 passed in 0.67s`
  - Exit status: `0`
- Detached frontend quality run: `logs/test-runs/phase2-frontend-green.log`
  - ESLint: passed
  - Vitest: `2` files passed, `14` tests passed
  - Next.js production build: passed
  - npm audit: `0` vulnerabilities
  - Exit status: `0`
- Secret scan: passed.
- Detached runner shell syntax check: passed.
- V2 marker scan for unfinished implementation terms: passed.

## Out of Scope

- No adverse retrieval query expansion.
- No strategy memo regeneration changes.
- No V2 UI stance panel.
- No database migration execution.
- No raw data upload.
- No change to V1.

## Next Phase

Phase 3 builds the adverse retrieval pipeline so V2 intentionally searches for authorities that weaken, limit, or contradict the client position.
