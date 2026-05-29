# V2 Phase 35 Release: Hosted Evidence Capture Plan

Phase 35 adds a secret-safe hosted evidence capture plan for Phase 34. It validates that local prerequisites are complete, defines the hosted environment variables required before evidence capture, and classifies signed smoke checks as audit-event-only so backend/DB evidence can be gathered without uncontrolled writes.

## Delivered

- `rag/evals/phase35_hosted_evidence_capture.json`: hosted evidence capture manifest.
- `scripts/build_phase35_hosted_evidence_capture_plan.py`: capture-plan report builder.
- `scripts/run_detached_quality_gate.sh`: `hosted-evidence-capture-plan` mode.
- `tests/test_phase35_hosted_evidence_capture.py`: coverage for local configuration readiness, hosted environment readiness, missing environment blockers, DB write classification blockers, missing prerequisite blockers, and CLI output.
- `Docs/v2_phase_35_hosted_evidence_capture_contract.md`: Phase 35 contract.
- `Docs/v2_phase_35_hosted_evidence_capture_runbook.md`: operator runbook.
- `Docs/v2_production_product_roadmap.md`: missing Phase 19 and Phase 20 roadmap entries restored, and Phase 35 added.

## Validation Evidence

Phase 35 validation evidence:

- Focused Phase 35 tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase35_hosted_evidence_capture.py -q`
  - Result: 7 passed.
- Python compile:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase35_hosted_evidence_capture_plan.py`
  - Result: passed.
- Detached Phase 35 gate:
  - Command: `scripts/run_detached_quality_gate.sh hosted-evidence-capture-plan phase35-hosted-evidence-capture-plan`
  - Log: `logs/test-runs/phase35-hosted-evidence-capture-plan.log`
  - Result: `ready_for_hosted_capture_configuration`, `exit_status=0`.
- Detached backend tests:
  - Command: `scripts/run_detached_quality_gate.sh tests phase35-hosted-evidence-tests`
  - Log: `logs/test-runs/phase35-hosted-evidence-tests.log`
  - Result: 359 passed, `exit_status=0`.
- Detached frontend quality:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase35-hosted-evidence-frontend`
  - Log: `logs/test-runs/phase35-hosted-evidence-frontend.log`
  - Result: lint passed, 17 Vitest tests passed, production build passed, npm audit found 0 vulnerabilities, `exit_status=0`.
- Secret scan:
  - Command: `python3 scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Scope: changed Phase 35 implementation, tests, and docs.
  - Result: no open development markers in changed Phase 35 files.

## Release Result

This release does not attach real hosted staging evidence. It creates the validated capture plan required before Phase 34 evidence is safely gathered.

The local Phase 35 status is expected to be `ready_for_hosted_capture_configuration`.

## Boundaries

- V1 remains untouched.
- Raw `data/` remains outside GitHub.
- No DB migration is applied.
- Phase 35 does not run hosted smoke checks from the local workspace.
