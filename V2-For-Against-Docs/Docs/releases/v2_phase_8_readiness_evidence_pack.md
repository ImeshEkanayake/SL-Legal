# V2 Phase 8 Release: Readiness Evidence Pack

## Release Goal

Phase 8 adds a deployment readiness evidence pack that turns release logs and production-stack reports into a structured go/no-go decision.

## Included

- `rag/evals/phase8_deployment_readiness_evidence.json`: evidence requirements manifest.
- `rag/sl_legal_rag/operations.py`: evidence validation, report evaluation, blocker detection, and readiness pack generation.
- `scripts/run_phase8_readiness_pack.py`: readiness pack builder.
- `scripts/run_detached_quality_gate.sh`: `readiness-pack` and `readiness-pack-production` modes.
- `Docs/v2_phase_8_readiness_evidence_contract.md`: evidence contract.
- `Docs/v2_phase_8_readiness_runbook.md`: local and production evidence runbook.
- `tests/test_phase8_readiness_pack.py`: readiness manifest and decision tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 8 is releasable when:

- Evidence manifest covers local release and production-stack checks.
- Focused tests prove ready and blocked decisions.
- Local readiness pack can return `ready` after detached Phase 8 gates pass.
- Production readiness pack records missing production-stack evidence until real reports are attached.
- Backend and frontend detached gates pass.
- Load-plan gate passes.
- Secret scan and marker scan pass.
- No V1 code, raw data, or database schema is changed.

## Validation Results

Local targeted validation completed on 2026-05-28:

- Focused Phase 8 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase8_readiness_pack.py -q`
  - Result: `4 passed in 0.02s`.
- Syntax checks:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/run_phase8_readiness_pack.py`
  - Result: passed.
- Initial local readiness-pack render:
  - Command: `PYTHONPATH=rag python3 scripts/run_phase8_readiness_pack.py --output logs/readiness/phase8-readiness-pack-local.json --allow-blockers`
  - Result: blocked before detached Phase 8 logs existed, as expected.
- Initial production readiness-pack render:
  - Command: `PYTHONPATH=rag python3 scripts/run_phase8_readiness_pack.py --include-production --output logs/readiness/phase8-readiness-pack-production-plan.json --allow-blockers`
  - Result: blocked with missing production-stack evidence, as expected.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.
- Detached backend tests:
  - Log: `logs/test-runs/phase8-tests.log`
  - Result: `251 passed in 0.84s`, exit `0`.
- Detached frontend quality:
  - Log: `logs/test-runs/phase8-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next.js build passed, `npm audit --audit-level=moderate` found `0` vulnerabilities, exit `0`.
- Detached load-plan gate:
  - Log: `logs/test-runs/phase8-load-plan.log`
  - Result: five-scenario plan rendered, exit `0`.
- Detached local readiness pack:
  - Log: `logs/test-runs/phase8-readiness-pack.log`
  - Result: decision `ready`, `3` passed, `0` failed, `0` missing, exit `0`.
- Detached production readiness pack review:
  - Log: `logs/test-runs/phase8-readiness-pack-production.log`
  - Result: decision `blocked`, `3` local evidence items passed, `6` production-stack evidence items missing, exit `0` because blocker recording was allowed for review.

## Production Deployment Note

This release does not claim a production cutover. Production deployment remains blocked until the production-stack readiness pack returns `ready` with schema, health, index, real-load, and searchability evidence attached.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No production cutover.

## Next Phase

The next phase can focus on running the production-stack evidence commands against hosted services and attaching the resulting reports as release artifacts.
