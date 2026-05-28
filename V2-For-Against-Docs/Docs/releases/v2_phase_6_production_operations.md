# V2 Phase 6 Release: Production Operations

## Release Goal

Phase 6 makes V2 operable as a production system. It adds the load-test scenario contract, load-test runner, detached load execution mode, operations runbook, observability guidance, release checklist, and tests for the operations contract.

## Included

- `rag/evals/phase6_load_scenarios.json`: canonical API load scenarios.
- `rag/sl_legal_rag/operations.py`: scenario parsing, placeholder substitution, percentile summaries, and threshold evaluation.
- `scripts/run_phase6_load_tests.py`: signed API load runner for local or staging stacks.
- `scripts/run_detached_quality_gate.sh`: new `load` and `load-plan` modes.
- `Docs/v2_phase_6_production_operations_contract.md`: Phase 6 operational contract.
- `Docs/v2_phase_6_operations_runbook.md`: release, metrics, incident, rollback, corpus audit, and data hydration workflow.
- `tests/test_phase6_operations.py`: tests for scenario coverage, substitution, thresholds, and fixture schema.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 6 is releasable when:

- API load scenarios cover workspace, retrieval, strategy validation, source viewer, and review queue paths.
- Load runner can execute signed requests under concurrency and produce p50/p95/p99/error-rate reports.
- Detached runner can start load plans and real load runs under separate PID/log files.
- Metrics and operations endpoints are documented.
- Release and incident runbooks exist.
- Backend and frontend detached gates pass.
- Load-plan dry run passes.
- Secret scan and marker scan pass.
- No V1 code, raw data, or database schema is changed.

## Validation Results

Local targeted validation completed on 2026-05-28:

- Focused Phase 6 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase6_operations.py -q`
  - Result: `4 passed in 0.01s`.
- Syntax checks:
  - Command: `python3 -m py_compile scripts/run_phase6_load_tests.py rag/sl_legal_rag/operations.py`
  - Result: passed.
- Load plan dry run:
  - Command: `python3 scripts/run_phase6_load_tests.py --dry-run`
  - Result: passed; five-scenario plan rendered.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.
- Detached backend tests:
  - Log: `logs/test-runs/phase6-tests-rerun.log`
  - Result: `242 passed in 0.71s`, exit `0`.
- Detached frontend quality:
  - Log: `logs/test-runs/phase6-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next.js build passed, `npm audit --audit-level=moderate` found `0` vulnerabilities, exit `0`.
- Detached load-plan gate:
  - Log: `logs/test-runs/phase6-load-plan-rerun.log`
  - Result: five-scenario plan rendered, exit `0`.

## Production Deployment Note

This release includes the real load runner and scenario thresholds. A production deployment should also run `scripts/run_detached_quality_gate.sh load phase6-load` against a production-like stack with representative `case_id`, `pack_id`, and `pack_item_id` environment variables. The dry-run validates the scenario contract; it is not a substitute for production-like load evidence.

## Out of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No infrastructure provisioning.
- No automated deployment cutover.

## Next Phase

The next phase can focus on production deployment automation, hosted data strategy, and recurring corpus/index quality monitoring.
