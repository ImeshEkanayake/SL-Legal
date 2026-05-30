# V2 Phase 38 Release: Hosted Capture Execution Orchestrator

Phase 38 adds a guarded orchestrator for the real hosted evidence path. It refreshes Phase 35, Phase 36, Phase 34, and Phase 37 readiness reports in sequence, stays dry-run by default, and only performs hosted HTTP capture when `--execute --include-environment` are both supplied.

## Delivered

- `rag/evals/phase38_hosted_capture_execution.json`: hosted capture execution manifest.
- `scripts/run_phase38_hosted_capture_execution.py`: chained execution orchestrator.
- `scripts/run_detached_quality_gate.sh`: `hosted-capture-execution` mode.
- `tests/test_phase38_hosted_capture_execution.py`: coverage for local awaiting state, hosted dry-run readiness, full accepted execution, pending DB validation, blocked execution, manifest validation, and CLI output.
- `Docs/v2_phase_38_hosted_capture_execution_contract.md`: Phase 38 contract.
- `Docs/v2_phase_38_hosted_capture_execution_runbook.md`: operator runbook.
- `Docs/v2_production_product_roadmap.md`: Phase 38 roadmap entry.

## Validation Evidence

Phase 38 validation evidence:

- Focused Phase 38 tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase38_hosted_capture_execution.py -q`
  - Result: 7 passed.
- Python compile:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/run_phase38_hosted_capture_execution.py`
  - Result: passed.
- Detached Phase 38 gate:
  - Command: `scripts/run_detached_quality_gate.sh hosted-capture-execution phase38-hosted-capture-execution`
  - Log: `logs/test-runs/phase38-hosted-capture-execution.log`
  - Result: `awaiting_hosted_capture_configuration`, `exit_status=0`.
- Detached backend tests:
  - Command: `scripts/run_detached_quality_gate.sh tests phase38-hosted-capture-execution-tests`
  - Log: `logs/test-runs/phase38-hosted-capture-execution-tests.log`
  - Result: 380 passed, `exit_status=0`.
- Detached frontend quality:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase38-hosted-capture-execution-frontend`
  - Log: `logs/test-runs/phase38-hosted-capture-execution-frontend.log`
  - Result: lint passed, 17 Vitest tests passed, production build passed, npm audit found 0 vulnerabilities, `exit_status=0`.
- Secret scan:
  - Command: `python3 scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Scope: changed Phase 38 implementation, tests, and docs.
  - Result: no open development markers in changed Phase 38 files.

## Release Result

This release does not execute hosted capture from the local workspace. It provides the guarded orchestrator for hosted staging execution.

The local Phase 38 status is expected to be `awaiting_hosted_capture_configuration`.

## Boundaries

- V1 remains untouched.
- Raw `data/` remains outside GitHub.
- No DB migration is applied.
- No hosted capture is executed unless `--execute --include-environment` are deliberately supplied.
