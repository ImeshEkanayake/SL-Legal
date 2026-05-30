# V2 Phase 37 Release: Hosted Capture Acceptance Gate

Phase 37 adds the post-capture acceptance gate for Phase 36 hosted evidence and Phase 34 backend/DB validation. It keeps local runs in `awaiting_hosted_capture_execution` and can only accept hosted capture after Phase 36 reports `hosted_evidence_captured`, Phase 34 reports `backend_db_staging_validated`, and all captured evidence passes status, field, and forbidden-content checks.

## Delivered

- `rag/evals/phase37_hosted_capture_acceptance.json`: hosted capture acceptance manifest.
- `scripts/build_phase37_hosted_capture_acceptance.py`: acceptance report builder.
- `scripts/run_detached_quality_gate.sh`: `hosted-capture-acceptance` mode.
- `tests/test_phase37_hosted_capture_acceptance.py`: coverage for local awaiting state, post-capture waiting, full acceptance, forbidden-content blockers, failed-runner blockers, and CLI output.
- `Docs/v2_phase_37_hosted_capture_acceptance_contract.md`: Phase 37 contract.
- `Docs/v2_phase_37_hosted_capture_acceptance_runbook.md`: operator runbook.
- `Docs/v2_production_product_roadmap.md`: Phase 37 roadmap entry.

## Validation Evidence

Phase 37 validation evidence:

- Focused Phase 37 tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase37_hosted_capture_acceptance.py -q`
  - Result: 7 passed.
- Python compile:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase37_hosted_capture_acceptance.py`
  - Result: passed.
- Detached Phase 37 gate:
  - Command: `scripts/run_detached_quality_gate.sh hosted-capture-acceptance phase37-hosted-capture-acceptance`
  - Log: `logs/test-runs/phase37-hosted-capture-acceptance.log`
  - Result: `awaiting_hosted_capture_execution`, `exit_status=0`.
- Detached backend tests:
  - Command: `scripts/run_detached_quality_gate.sh tests phase37-hosted-capture-acceptance-tests`
  - Log: `logs/test-runs/phase37-hosted-capture-acceptance-tests.log`
  - Result: 373 passed, `exit_status=0`.
- Detached frontend quality:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase37-hosted-capture-acceptance-frontend`
  - Log: `logs/test-runs/phase37-hosted-capture-acceptance-frontend.log`
  - Result: lint passed, 17 Vitest tests passed, production build passed, npm audit found 0 vulnerabilities, `exit_status=0`.
- Secret scan:
  - Command: `python3 scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Scope: changed Phase 37 implementation, tests, and docs.
  - Result: no open development markers in changed Phase 37 files.

## Release Result

This release does not execute hosted capture. It provides the acceptance gate for evidence produced by Phase 36 and validated by Phase 34.

The local Phase 37 status is expected to be `awaiting_hosted_capture_execution`.

## Boundaries

- V1 remains untouched.
- Raw `data/` remains outside GitHub.
- No DB migration is applied.
- No hosted smoke check is executed by Phase 37.
