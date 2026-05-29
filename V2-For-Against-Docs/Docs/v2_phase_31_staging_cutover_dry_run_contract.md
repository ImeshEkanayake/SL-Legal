# V2 Phase 31 Contract: Staging Cutover Dry Run

## Purpose

Phase 31 converts Phase 30 readiness into a non-mutating staging cutover plan for the V2 lawyer workspace UI.

The phase does not deploy the application and does not write to the shared database. It produces a dry-run report that tells the operator whether the local release is ready for hosted environment setup or whether a hosted staging environment is already ready for cutover review.

## Scope

Included:

- Staging cutover dry-run manifest at `rag/evals/phase31_staging_cutover_dry_run.json`.
- Dry-run report builder at `scripts/build_phase31_staging_cutover_dry_run.py`.
- Detached gate mode `staging-cutover-dry-run`.
- Smoke-test command plan for hosted env readiness, browser workflow, backend regression tests, and frontend quality.
- Manual approval and rollback checklist.

Excluded:

- V1 changes.
- Raw data upload.
- Database migration or database writes.
- Production or staging deployment execution.
- Printing secret values into logs or reports.

## Statuses

`ready_for_hosted_env_setup` means the Phase 30 readiness report is present and accepted, but the report used local evidence only. This is the expected status in normal local Git work.

`ready_for_staging_cutover` means the Phase 30 report was generated with hosted environment inspection and returned `ready_for_deployment_review`.

`blocked` means required evidence is missing, the Phase 30 readiness status is not accepted, smoke command definitions are invalid, or rollback/manual approval metadata is incomplete.

## Required Inputs

The dry run requires:

- `logs/readiness/phase30-ui-deployment-readiness.json`
- `rag/evals/phase30_ui_deployment_readiness.json`
- `Docs/v2_phase_30_ui_deployment_readiness_contract.md`
- `Docs/v2_phase_30_ui_deployment_readiness_runbook.md`
- `Docs/releases/v2_phase_30_ui_deployment_readiness.md`

The Phase 30 report must have status `ready_for_hosted_env_review` or `ready_for_deployment_review`.

## Smoke Commands

Local smoke commands:

```bash
scripts/run_detached_quality_gate.sh phase29-browser-workflow phase31-staging-browser-smoke
scripts/run_detached_quality_gate.sh tests phase31-staging-tests
scripts/run_detached_quality_gate.sh frontend phase31-staging-frontend
```

Hosted staging environment command:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness-env phase31-staging-env-readiness
```

Phase 31 report command:

```bash
scripts/run_detached_quality_gate.sh staging-cutover-dry-run phase31-staging-cutover-dry-run
```

## Acceptance Criteria

- Phase 30 readiness evidence is present and accepted.
- The dry-run report is generated without printing secret values.
- Smoke commands are listed with expected detached-log evidence paths.
- Rollback steps and manual approvals are explicit.
- Local result is at least `ready_for_hosted_env_setup`.
- Hosted staging result becomes `ready_for_staging_cutover` only after Phase 30 env validation passes in the hosted environment.
- Detached backend tests, frontend quality gate, staging cutover dry run, secret scan, and marker scan pass.
