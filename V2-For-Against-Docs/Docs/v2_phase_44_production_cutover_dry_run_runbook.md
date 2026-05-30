# V2 Phase 44 Runbook: Production Cutover Dry Run

## Purpose

Use this runbook to build the Phase 44 production cutover dry-run report after Phase 43 readiness passes.

Phase 44 does not execute production. It records the dry-run command plan, expected evidence paths, rollback plan, and approval expectations.

## Inputs

Required committed inputs:

- `rag/evals/phase44_production_cutover_dry_run.json`
- `Docs/v2_phase_44_production_cutover_dry_run_contract.md`
- Phase 43 manifest, contract, runbook, release note, and builder

Required ignored evidence:

- `logs/readiness/phase43-production-cutover-readiness.json`

Expected dry-run evidence paths recorded by the report include:

- `logs/test-runs/phase44-production-env-inventory.log`
- `logs/test-runs/phase44-production-tests.log`
- `logs/test-runs/phase44-production-frontend.log`
- `logs/production-cutover/phase44-prebuilt-production-deploy-plan.json`
- `logs/test-runs/phase44-production-post-deploy-smoke.log`
- `logs/production-cutover/phase44-index-refresh-plan.json`
- `logs/production-cutover/phase44-lawyer-owner-dry-run-acceptance.json`
- `logs/production-cutover/phase44-operator-dry-run-acceptance.json`
- `logs/production-cutover/phase44-rollback-alias-plan.json`
- `logs/production-cutover/phase44-revoke-access-plan.json`
- `logs/production-cutover/phase44-failure-evidence-register.json`

## Local Gate

Run the detached gate:

```bash
scripts/run_detached_quality_gate.sh production-cutover-dry-run phase44-production-cutover-dry-run
```

Expected local status before Phase 43 is ready:

```text
awaiting_production_cutover_readiness
```

## Step Safety

Read-only dry-run steps can be run as ordinary detached checks.

Planned-only steps are recorded for review but must not be executed in Phase 44. This includes:

- production deployment;
- release promotion;
- rollback;
- database migration;
- raw data upload;
- index mutation.

## Decision Interpretation

- `awaiting_production_cutover_readiness`: finish Phase 43 readiness first.
- `production_cutover_dry_run_planned`: Phase 45 execution planning can start.
- `blocked`: inspect `blockers`, repair the step definition or readiness evidence, and rerun Phase 44.

## Safety Rules

- Do not commit ignored `logs/` evidence.
- Do not upload raw `data/`.
- Do not expose secret values in reports.
- Do not apply a database migration.
- Do not execute production traffic.
- Do not promote a release.
- Do not execute rollback.
- Do not change V1.
- Do not describe any generated report as final legal advice.
