# V2 Phase 36 Release: Hosted Evidence Capture Runner

Phase 36 adds the guarded hosted evidence runner for Phase 34 backend/DB staging evidence. It remains dry-run by default and performs real hosted HTTP capture only when `--execute --include-environment` are both supplied.

## Delivered

- `rag/evals/phase36_hosted_evidence_capture_runner.json`: hosted evidence capture runner manifest.
- `scripts/run_phase36_hosted_evidence_capture.py`: dry-run and hosted execution runner.
- `scripts/run_detached_quality_gate.sh`: `hosted-evidence-capture-runner` mode.
- `tests/test_phase36_hosted_evidence_capture_runner.py`: coverage for dry-run readiness, hosted-ready state, scrubbed evidence output, execution blockers, response-shape blockers, and CLI output.
- `Docs/v2_phase_36_hosted_evidence_capture_runner_contract.md`: Phase 36 contract.
- `Docs/v2_phase_36_hosted_evidence_capture_runner_runbook.md`: operator runbook.
- `Docs/v2_production_product_roadmap.md`: Phase 36 roadmap entry.

## Validation Evidence

Phase 36 validation evidence:

- Focused Phase 36 tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase36_hosted_evidence_capture_runner.py -q`
  - Result: 7 passed.
- Python compile:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/run_phase36_hosted_evidence_capture.py`
  - Result: passed.
- Detached Phase 36 gate:
  - Command: `scripts/run_detached_quality_gate.sh hosted-evidence-capture-runner phase36-hosted-evidence-capture-runner`
  - Log: `logs/test-runs/phase36-hosted-evidence-capture-runner.log`
  - Result: `ready_for_hosted_capture_runner_configuration`, `exit_status=0`.
- Detached backend tests:
  - Command: `scripts/run_detached_quality_gate.sh tests phase36-hosted-evidence-runner-tests-final`
  - Log: `logs/test-runs/phase36-hosted-evidence-runner-tests-final.log`
  - Result: 366 passed, `exit_status=0`.
- Detached frontend quality:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase36-hosted-evidence-runner-frontend`
  - Log: `logs/test-runs/phase36-hosted-evidence-runner-frontend.log`
  - Result: lint passed, 17 Vitest tests passed, production build passed, npm audit found 0 vulnerabilities, `exit_status=0`.
- Secret scan:
  - Command: `python3 scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Scope: changed Phase 36 implementation, tests, and docs.
  - Result: no open development markers in changed Phase 36 files.

## Release Result

This release does not execute hosted capture from the local workspace. It provides the guarded runner that can execute inside hosted staging after Phase 35 configuration is ready.

The local Phase 36 status is expected to be `ready_for_hosted_capture_runner_configuration`.

## Boundaries

- V1 remains untouched.
- Raw `data/` remains outside GitHub.
- No DB migration is applied.
- No hosted smoke check is executed unless the operator explicitly passes `--execute --include-environment`.
