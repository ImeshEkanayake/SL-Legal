# V2 Phase 7 Release: Deployment Automation And Corpus Monitoring

## Release Goal

Phase 7 makes deployment readiness, hosted-data operations, and recurring monitoring repeatable through a reviewed manifest and machine-readable reports.

## Included

- `rag/evals/phase7_deployment_monitoring_manifest.json`: command manifest for release gates, deployment readiness, hosted data, and recurring monitoring.
- `rag/sl_legal_rag/operations.py`: operational manifest validation, command rendering, and plan generation.
- `scripts/run_phase7_operational_plan.py`: JSON, shell, and Markdown plan renderer.
- `scripts/run_phase7_monitoring_snapshot.py`: monitoring snapshot planner and controlled executor.
- `Docs/v2_phase_7_deployment_monitoring_contract.md`: Phase 7 contract.
- `Docs/v2_phase_7_hosted_data_strategy.md`: hosted data strategy.
- `tests/test_phase7_operations.py`: contract tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 7 is releasable when:

- Manifest covers release gates, deployment readiness, hosted data, and recurring monitoring.
- Operational plan renders JSON, shell, and Markdown.
- Monitoring snapshot writes machine-readable plan evidence.
- Production-stack commands are explicitly flagged.
- Backend and frontend detached gates pass.
- Load-plan gate passes.
- Secret scan and marker scan pass.
- No V1 code, raw data, or database schema is changed.

## Validation Results

Local targeted validation completed on 2026-05-28:

- Focused Phase 7 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase7_operations.py -q`
  - Result: `5 passed in 0.02s`.
- Syntax checks:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/run_phase7_operational_plan.py scripts/run_phase7_monitoring_snapshot.py`
  - Result: passed.
- Operational release plan render:
  - Command: `PYTHONPATH=rag python3 scripts/run_phase7_operational_plan.py --section release_gates --format json`
  - Result: passed.
- Monitoring plan render:
  - Command: `PYTHONPATH=rag python3 scripts/run_phase7_monitoring_snapshot.py --output logs/monitoring/phase7-monitoring-plan.json`
  - Result: passed.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.
- Detached backend tests:
  - Log: `logs/test-runs/phase7-tests.log`
  - Result: `247 passed in 0.78s`, exit `0`.
- Detached frontend quality:
  - Log: `logs/test-runs/phase7-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next.js build passed, `npm audit --audit-level=moderate` found `0` vulnerabilities, exit `0`.
- Detached load-plan gate:
  - Log: `logs/test-runs/phase7-load-plan.log`
  - Result: five-scenario plan rendered, exit `0`.

## Production Deployment Note

This phase ships automation and monitoring contracts. A production deployment still needs the `deployment_readiness` section to run against a representative stack with service credentials, indexed corpus data, and signed load-test environment variables.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No hosted infrastructure provisioning.
- No production cutover.

## Next Phase

The next phase can focus on executing the production-like deployment readiness section against hosted services and attaching real load, searchability, and index-consistency evidence.
