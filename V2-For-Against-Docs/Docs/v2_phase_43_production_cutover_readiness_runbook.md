# V2 Phase 43 Runbook: Production Cutover Readiness Pack

## Purpose

Use this runbook to build the Phase 43 production cutover readiness pack after Phase 42 staging acceptance is complete.

Phase 43 does not execute production. It only decides whether Phase 44 dry-run planning can start.

## Inputs

Required committed inputs:

- `rag/evals/phase43_production_cutover_readiness.json`
- `Docs/v2_phase_43_production_cutover_readiness_contract.md`
- Phase 42 manifest, contract, runbook, release note, and builder

Required ignored evidence:

- `logs/readiness/phase42-staging-acceptance-decision.json`
- `logs/release-artifacts/phase43-release-provenance-ledger.json`
- `logs/release-artifacts/phase43-signing-plan.json`
- `logs/production-cutover/phase43-schema-readiness.json`
- `logs/production-cutover/phase43-rag-index-health.json`
- `logs/production-cutover/phase43-signed-load-suite.json`
- `logs/production-cutover/phase43-corpus-searchability.json`
- `logs/production-cutover/phase43-rollback-schema-smoke.json`
- `logs/production-cutover/phase43-rollback-checklist.json`
- `logs/production-cutover/phase43-incident-response-checklist.json`

## Local Gate

Run the detached gate:

```bash
scripts/run_detached_quality_gate.sh production-cutover-readiness phase43-production-cutover-readiness
```

Expected local status before Phase 42 is accepted:

```text
awaiting_staging_acceptance
```

## Environment Gate

Run only in the reviewed production-planning environment:

```bash
scripts/run_detached_quality_gate.sh production-cutover-readiness-env phase43-production-cutover-readiness-env
```

The environment gate does not print secret values. It records only presence, length checks, URL shape checks, and fixed expected-value checks.

## Required Evidence Shapes

Schema readiness:

```json
{
  "status": "ready",
  "db_migration_applied": false,
  "production_mutation_executed": false
}
```

Rollback schema smoke:

```json
{
  "status": "passed",
  "rollback_only": true,
  "migration_applied": false,
  "production_mutation_executed": false
}
```

Rollback checklist:

```json
{
  "status": "accepted",
  "rollback_owner_assigned": true,
  "tested_rollback_only": true,
  "production_execution_authorized": false,
  "production_mutation_executed": false
}
```

Incident response checklist:

```json
{
  "status": "accepted",
  "incident_owner_assigned": true,
  "monitoring_window_defined": true,
  "lawyer_review_required": true,
  "production_execution_authorized": false
}
```

## Decision Interpretation

- `awaiting_staging_acceptance`: finish Phase 42 hosted staging acceptance first.
- `awaiting_production_readiness_evidence`: collect production-readiness and rollback evidence.
- `awaiting_production_environment_inventory`: run the reviewed environment inventory gate.
- `ready_for_production_cutover_dry_run`: Phase 44 dry-run planning can start.
- `blocked`: inspect `blockers`, repair the evidence, and rerun Phase 43.

## Safety Rules

- Do not commit ignored `logs/` evidence.
- Do not upload raw `data/`.
- Do not expose secret values in reports.
- Do not apply a database migration.
- Do not execute production traffic.
- Do not change V1.
- Do not describe any generated report as final legal advice.
