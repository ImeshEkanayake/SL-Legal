# V2 Phase 28 Release: Authority Workflow UI Integration

## Release Goal

Phase 28 makes the existing authority expansion backend usable from the lawyer workspace. A reviewer can now execute a planned authority search, verify the resulting child pack, and promote verified authority items from the reasoning panel.

## Included

- `web/src/lib/workspace-types.ts`: authority workflow action input and response contracts.
- `web/src/lib/workspace-api.ts`: signed API clients for execute, verify, and promote.
- `web/src/app/actions.ts`: server actions that revalidate the workspace after successful workflow calls.
- `web/src/app/page.tsx`: workspace action wiring.
- `web/src/components/CaseWorkspace.tsx`: local draft-plan updates and refresh after authority workflow actions.
- `web/src/components/DocumentWorkspace.tsx`: reasoning-panel controls and status displays for execution, verification, and promotion.
- `web/src/components/CaseWorkspace.test.tsx`: focused Execute -> Verify -> Promote UI test.
- `Docs/v2_phase_28_authority_workflow_ui_contract.md`: UI integration contract.
- `Docs/v2_production_product_roadmap.md`: Phase 28 roadmap entry.
- `Docs/v2_codebase_map.md`: Phase 28 code map entry.

## Validation Results

Detached validation completed on 2026-05-30:

- Backend test suite:
  - Command: `scripts/run_detached_quality_gate.sh tests phase28-authority-workflow-ui-tests`
  - Log: `logs/test-runs/phase28-authority-workflow-ui-tests.log`
  - Result: `317 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase28-authority-workflow-ui-frontend`
  - Log: `logs/test-runs/phase28-authority-workflow-ui-frontend.log`
  - Result: ESLint passed, Vitest `17 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Safety Boundary

- No V1 changes.
- No raw data upload.
- No database migration.
- No raw data or generated tracking artifacts are committed to normal Git.
- Backend validation remains authoritative for reservations, duplicate execution, source verification, and controlled promotion.

## Next Phase

The next step should run a browser-level workflow check against a representative matter, then capture screenshot/API evidence for the lawyer-facing end-to-end authority promotion journey.
