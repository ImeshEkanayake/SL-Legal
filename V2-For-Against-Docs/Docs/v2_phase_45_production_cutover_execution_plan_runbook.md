# V2 Phase 45 Runbook: Production Cutover Execution Plan

## Purpose

Use this runbook to build the reviewed production cutover execution plan after Phase 44 dry-run planning is complete.

Phase 45 does not execute production. It records the plan and the approval evidence required before any future production execution.

## Inputs

Required committed inputs:

- `rag/evals/phase45_production_cutover_execution_plan.json`
- `Docs/v2_phase_45_production_cutover_execution_plan_contract.md`
- Phase 44 manifest, contract, runbook, release note, and builder

Required ignored evidence:

- `logs/readiness/phase44-production-cutover-dry-run.json`
- `logs/production-cutover/phase45-lawyer-owner-execution-plan-signoff.json`
- `logs/production-cutover/phase45-operator-execution-plan-signoff.json`
- `logs/production-cutover/phase45-legal-review-signoff.json`

## Local Gate

Run the detached gate:

```bash
scripts/run_detached_quality_gate.sh production-cutover-execution-plan phase45-production-cutover-execution-plan
```

Expected local status before Phase 44 is planned:

```text
awaiting_production_cutover_dry_run
```

## Approval File Shapes

Lawyer-owner sign-off:

```json
{
  "status": "accepted",
  "reviewed_phase44_dry_run": true,
  "reviewed_execution_commands": true,
  "lawyer_review_required": true,
  "no_final_legal_advice": true,
  "production_execution_authorized": false
}
```

Operator sign-off:

```json
{
  "status": "accepted",
  "reviewed_phase44_dry_run": true,
  "rollback_points_confirmed": true,
  "production_execution_authorized": false,
  "database_migration_authorized": false,
  "raw_data_upload_authorized": false
}
```

Legal-review sign-off:

```json
{
  "status": "accepted",
  "lawyer_review_required": true,
  "no_final_legal_advice": true,
  "production_execution_authorized": false
}
```

## Command Safety

Commands that mutate production, promote a release, migrate a database, upload raw data, or mutate an index must include:

- an explicit execution flag;
- a rollback point;
- `execution_approved=false`.

Phase 45 should fail if any command already authorizes execution.

## Decision Interpretation

- `awaiting_production_cutover_dry_run`: finish Phase 44 first.
- `awaiting_execution_approvals`: collect lawyer-owner, operator, and legal-review sign-off evidence.
- `production_cutover_execution_plan_ready`: the execution plan is ready for final human review.
- `blocked`: inspect `blockers`, repair evidence or command definitions, and rerun Phase 45.

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
