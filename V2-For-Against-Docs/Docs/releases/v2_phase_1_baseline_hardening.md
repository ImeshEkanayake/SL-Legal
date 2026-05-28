# V2 Phase 1 Release: Baseline Hardening

## Release Goal

Phase 1 establishes the production baseline for V2 before feature implementation begins. This release makes the V2 direction explicit, documents the codebase, defines the required test layers, and provides detached test execution so long checks run under their own PID and log file.

## Included

- Production roadmap for claim-level support, adverse, mixed, and context evidence.
- Engineering and testing playbook covering unit, integration, retrieval evaluation, E2E, load, and release gates.
- Codebase map for backend, frontend, SQL, scripts, tests, and V2 expansion points.
- Detached quality gate runner:
  - `scripts/run_detached_quality_gate.sh full`
  - `scripts/run_detached_quality_gate.sh backend`
  - `scripts/run_detached_quality_gate.sh frontend`
  - `scripts/run_detached_quality_gate.sh tests`
- Git ignore updates for detached test logs and PID files.
- V2 `VERSION.md` links to the new planning docs.

## Production Readiness Criteria

Phase 1 is releasable when:

- Shell syntax validation passes for the detached runner.
- Secret scan passes.
- New docs do not trip the repository quality marker scan.
- V2 quality workflow specification is prepared for GitHub activation.
- A detached backend or test quality run has a PID file, log file, and auditable result.

## Validation Results

Local validation completed on 2026-05-28:

- Detached backend test run: `logs/test-runs/phase1-tests-green.log`
  - Result: `214 passed in 8.71s`
  - Exit status: `0`
- Detached frontend quality run: `logs/test-runs/phase1-frontend-green.log`
  - ESLint: passed
  - Vitest: `2` files passed, `14` tests passed
  - Next.js production build: passed
  - npm audit: `0` vulnerabilities
  - Exit status: `0`
- Secret scan: passed.
- Detached runner shell syntax check: passed.

## Known Follow-up

GitHub Actions activation is pending because the current GitHub OAuth token does not include the `workflow` scope. GitHub rejected the root workflow push with:

`refusing to allow an OAuth App to create or update workflow '.github/workflows/v2-quality.yml' without 'workflow' scope`

After re-authenticating GitHub CLI with workflow scope, add the prepared root-level V2 quality workflow so pull requests and releases run the same backend and frontend gates automatically.

## Out of Scope

- No claim-level evidence assessment schema changes.
- No database migration execution.
- No V2 UI behavior changes.
- No raw data upload.
- No change to V1.

## Next Phase

Phase 2 builds the evidence assessment domain model and persistence contract for support, adverse, mixed, and context evidence.
