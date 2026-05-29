# V2 Phase 32 Release: Hosted Staging Execution Pack

## Summary

Phase 32 adds a hosted staging execution pack for the V2 lawyer workspace UI. It turns Phase 31 dry-run evidence into a concrete hosted-execution checklist, adds a secret-safe report builder, and provides a private signed UI session token utility for lawyer review.

## Added

- `rag/evals/phase32_hosted_staging_execution.json`: hosted staging execution manifest.
- `scripts/build_phase32_hosted_staging_execution_pack.py`: execution-pack report builder.
- `scripts/create_ui_session_token.py`: private UI session token utility for hosted staging review.
- `scripts/run_detached_quality_gate.sh`: `hosted-staging-execution-pack` mode.
- `tests/test_phase32_hosted_staging_execution_pack.py`: coverage for manifest loading, execution states, blockers, CLI output, and session-token shape.
- `Docs/v2_phase_32_hosted_staging_execution_contract.md`: Phase 32 contract.
- `Docs/v2_phase_32_hosted_staging_execution_runbook.md`: operator runbook.

## Validation

Phase 32 validation evidence:

- Focused tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase32_hosted_staging_execution_pack.py -q`
  - Result: `7 passed`
- Syntax check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase32_hosted_staging_execution_pack.py scripts/create_ui_session_token.py`
  - Result: passed
- Hosted staging execution-pack gate:
  - Command: `scripts/run_detached_quality_gate.sh hosted-staging-execution-pack phase32-hosted-staging-execution-pack`
  - Log: `logs/test-runs/phase32-hosted-staging-execution-pack.log`
  - Expected local status: `ready_for_hosted_configuration`
  - Result: `ready_for_hosted_configuration`, `exit_status=0`
- Backend regression tests:
  - Command: `scripts/run_detached_quality_gate.sh tests phase32-hosted-tests`
  - Log: `logs/test-runs/phase32-hosted-tests.log`
  - Result: `338 passed`, `exit_status=0`
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase32-hosted-frontend`
  - Log: `logs/test-runs/phase32-hosted-frontend.log`
  - Result: lint passed, `17` Vitest tests passed, production build passed, `0` moderate-or-higher audit vulnerabilities, `exit_status=0`
- Secret scan:
  - Command: `python3 scripts/check_no_plaintext_secrets.py`
  - Result: passed
- Marker scan:
  - Scope: changed Phase 32 implementation, tests, and docs.
  - Result: no open development markers in changed Phase 32 files.

## Deployment Note

The local Phase 32 status is expected to be `ready_for_hosted_configuration`. It becomes `ready_for_hosted_staging_execution` only after the hosted staging environment runs Phase 31 with hosted environment validation and returns `ready_for_staging_cutover`.

## Clean Staging Repo Check

After syncing V2 into the clean GitHub staging repo, the staging copy also passed:

- Phase 32 hosted staging execution pack: `ready_for_hosted_configuration`, `exit_status=0`
- Backend regression tests: `338 passed`, `exit_status=0`
- Frontend quality gate: lint passed, `17` Vitest tests passed, production build passed, `0` moderate-or-higher audit vulnerabilities, `exit_status=0`
- Secret scan: passed
- Changed-file marker scan: no matches
