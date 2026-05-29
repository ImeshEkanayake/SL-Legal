# V2 Phase 31 Release: Staging Cutover Dry Run

## Summary

Phase 31 adds a non-mutating staging cutover dry-run gate for the V2 lawyer workspace UI. It consumes Phase 30 readiness evidence, produces operator-safe staging smoke commands, and separates local readiness from true hosted staging cutover readiness.

## Added

- `rag/evals/phase31_staging_cutover_dry_run.json`: staging cutover manifest.
- `scripts/build_phase31_staging_cutover_dry_run.py`: dry-run report builder.
- `scripts/run_detached_quality_gate.sh`: `staging-cutover-dry-run` mode.
- `tests/test_phase31_staging_cutover_dry_run.py`: coverage for manifest loading, accepted Phase 30 statuses, missing evidence blockers, rollback validation, and CLI output.
- `Docs/v2_phase_31_staging_cutover_dry_run_contract.md`: Phase 31 contract.
- `Docs/v2_phase_31_staging_cutover_dry_run_runbook.md`: operator runbook.

## Validation

Phase 31 validation evidence:

- Focused tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase31_staging_cutover_dry_run.py -q`
  - Result: `7 passed`
- Syntax check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase31_staging_cutover_dry_run.py`
  - Result: passed
- Staging cutover dry-run gate:
  - Command: `scripts/run_detached_quality_gate.sh staging-cutover-dry-run phase31-staging-cutover-dry-run`
  - Log: `logs/test-runs/phase31-staging-cutover-dry-run.log`
  - Expected local status: `ready_for_hosted_env_setup`
  - Result: `ready_for_hosted_env_setup`, `exit_status=0`
- Backend regression tests:
  - Command: `scripts/run_detached_quality_gate.sh tests phase31-staging-tests`
  - Log: `logs/test-runs/phase31-staging-tests.log`
  - Result: `331 passed`, `exit_status=0`
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase31-staging-frontend`
  - Log: `logs/test-runs/phase31-staging-frontend.log`
  - Result: lint passed, `17` Vitest tests passed, production build passed, `0` moderate-or-higher audit vulnerabilities, `exit_status=0`
- Secret scan:
  - Command: `python3 scripts/check_no_plaintext_secrets.py`
  - Result: passed
- Marker scan:
  - Scope: changed Phase 31 implementation, tests, and docs.
  - Result: no open development markers in changed Phase 31 files.

## Deployment Note

The local Phase 31 status is expected to be `ready_for_hosted_env_setup`. It becomes `ready_for_staging_cutover` only after the hosted staging environment runs Phase 30 with `--include-environment` and passes without exposing secret values.

## Clean Staging Repo Check

After syncing V2 into the clean GitHub staging repo, the staging copy also passed:

- Phase 30 UI deployment readiness: `ready_for_hosted_env_review`, `exit_status=0`
- Phase 31 staging cutover dry run: `ready_for_hosted_env_setup`, `exit_status=0`
- Backend regression tests: `331 passed`, `exit_status=0`
- Frontend quality gate: lint passed, `17` Vitest tests passed, production build passed, `0` moderate-or-higher audit vulnerabilities, `exit_status=0`
- Secret scan: passed
- Changed-file marker scan: no matches
