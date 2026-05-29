# V2 Phase 29 Release: Browser Workflow Validation

## Release Goal

Phase 29 adds real-browser evidence for the V2 authority workflow. The validation loads a representative matter in the real Next workspace, clicks Execute -> Verify -> Promote, and captures signed API-call evidence without touching the shared database.

## Included

- `web/scripts/run-phase29-browser-workflow.mjs`: browser workflow validation runner with temporary signed fake backend.
- `web/package.json`: `phase29:e2e` script.
- `web/package-lock.json`: locked `playwright-core` dependency.
- `scripts/run_detached_quality_gate.sh`: `phase29-browser-workflow` detached mode.
- `Docs/v2_phase_29_browser_workflow_validation_contract.md`: browser validation contract.
- `Docs/v2_production_product_roadmap.md`: Phase 29 roadmap entry.
- `Docs/v2_codebase_map.md`: Phase 29 code map entry.

## Validation Results

Detached validation completed on 2026-05-30:

- Phase 29 browser workflow validation:
  - Command: `scripts/run_detached_quality_gate.sh phase29-browser-workflow phase29-browser-workflow-validation`
  - Log: `logs/test-runs/phase29-browser-workflow-validation.log`
  - Result: passed; Chrome rendered the representative matter, completed Execute -> Verify -> Promote, observed signed API calls, and reported no hydration mismatch with extensions disabled.
  - Local evidence:
    - `logs/phase29-browser-workflow/phase29-browser-workflow-report.json`
    - `logs/phase29-browser-workflow/phase29-browser-workflow-summary.md`
    - `logs/phase29-browser-workflow/phase29-authority-workflow.png`
    - `logs/phase29-browser-workflow/phase29-next-dev.log`
- Backend test suite:
  - Command: `scripts/run_detached_quality_gate.sh tests phase29-browser-workflow-tests`
  - Log: `logs/test-runs/phase29-browser-workflow-tests.log`
  - Result: `317 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase29-browser-workflow-frontend-final`
  - Log: `logs/test-runs/phase29-browser-workflow-frontend-final.log`
  - Result: ESLint passed, Vitest `17 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Safety Boundary

- No V1 changes.
- No raw data upload.
- No database migration.
- No database writes.
- Browser evidence under `logs/` remains local and is not committed to normal Git.

## Next Phase

The next step should add a production deployment readiness checklist for the UI path, including hosted environment variables, signed-session setup, and representative browser smoke validation instructions for staging.
