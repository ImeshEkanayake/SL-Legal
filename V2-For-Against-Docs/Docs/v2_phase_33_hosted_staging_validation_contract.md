# V2 Phase 33 Contract: Hosted Staging Execution Validation

## Purpose

Phase 33 validates real hosted staging execution evidence for the V2 lawyer workspace UI.

Local runs are expected to stop at `awaiting_hosted_execution`. The report becomes `hosted_staging_validated` only after hosted environment readiness, hosted cutover readiness, hosted execution-pack readiness, smoke logs, operator review, and lawyer-owner acceptance evidence are attached.

## Scope

Included:

- Hosted staging validation manifest at `rag/evals/phase33_hosted_staging_validation.json`.
- Validation report builder at `scripts/build_phase33_hosted_staging_validation.py`.
- Detached gate mode `hosted-staging-validation`.
- Tests for local pending state, full hosted validation, blockers, and CLI output.

Excluded:

- V1 changes.
- Raw data upload.
- Database migration or database writes.
- Direct deployment-platform mutation from the local workspace.
- Hosted secret values, session tokens, or raw corpus artifacts in Git.

## Statuses

`awaiting_hosted_execution` means Phase 32 prerequisites are valid, but one or more hosted-only evidence files are missing or still pending.

`hosted_staging_validated` means all required hosted staging evidence is present and verified.

`blocked` means a prerequisite is missing or failed, or hosted evidence exists with a failed/unaccepted status.

## Required Prerequisites

- `logs/readiness/phase32-hosted-staging-execution-pack.json`
- `rag/evals/phase32_hosted_staging_execution.json`
- `Docs/v2_phase_32_hosted_staging_execution_contract.md`
- `Docs/v2_phase_32_hosted_staging_execution_runbook.md`
- `Docs/releases/v2_phase_32_hosted_staging_execution.md`

The Phase 32 report may be `ready_for_hosted_configuration` locally, or `ready_for_hosted_staging_execution` after hosted execution.

## Required Hosted Evidence

- `logs/readiness/phase30-ui-deployment-readiness-env.json` with status `ready_for_deployment_review`.
- `logs/readiness/phase31-staging-cutover-dry-run.json` with status `ready_for_staging_cutover`.
- `logs/readiness/phase32-hosted-staging-execution-pack.json` with status `ready_for_hosted_staging_execution`.
- `logs/test-runs/phase33-platform-browser-smoke.log` with `exit_status=0`.
- `logs/test-runs/phase33-platform-tests.log` with `exit_status=0`.
- `logs/test-runs/phase33-platform-frontend.log` with `exit_status=0`.
- `logs/hosted-staging/phase33-operator-secret-review.json` with status `approved`.
- `logs/hosted-staging/phase33-lawyer-owner-acceptance.json` with status `accepted`.

## Acceptance Criteria

- Local gate exits successfully with `awaiting_hosted_execution`.
- Hosted gate exits successfully with `hosted_staging_validated` only after all hosted evidence is present.
- Failed hosted evidence blocks the report.
- Reports contain evidence hashes and statuses, not secret values or session tokens.
- Detached backend tests, frontend quality gate, Phase 33 validation gate, secret scan, and marker scan pass.
