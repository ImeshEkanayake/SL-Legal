# V2 Phase 44 Contract: Production Cutover Dry Run

## Purpose

Phase 44 rehearses the production cutover procedure without mutating production data.

This phase is a dry-run planner. It does not execute production deployment, release promotion, database migration, index mutation, raw data upload, rollback, or signing.

## Implementation Surface

- Manifest: `rag/evals/phase44_production_cutover_dry_run.json`
- Dry-run builder: `scripts/build_phase44_production_cutover_dry_run.py`
- Detached gate mode: `production-cutover-dry-run`
- Report output: `logs/readiness/phase44-production-cutover-dry-run.json`

## Status Values

- `awaiting_production_cutover_readiness`: Phase 43 has not returned `ready_for_production_cutover_dry_run`.
- `production_cutover_dry_run_planned`: Phase 43 is ready and every dry-run, approval, and rollback step is safe for the dry-run boundary.
- `blocked`: prerequisites failed, readiness evidence failed, forbidden content was found, an ordered step is incomplete, or a mutating action is not planned-only.

## Required Inputs

Phase 44 consumes:

- Phase 43 readiness manifest, contract, runbook, release note, and builder;
- Phase 43 readiness report at `logs/readiness/phase43-production-cutover-readiness.json`;
- ordered preflight, deployment, verification, rollback, and owner-approval step definitions;
- forbidden-content rules for secrets, raw response bodies, DB URLs, private keys, and final legal advice language.

## Dry-Run Step Rules

Each dry-run step must declare:

- `stage`
- `owner`
- `execution_mode`
- `expected_evidence`
- risk flags for production mutation, database migration, raw data upload, index mutation, and release promotion

Allowed execution modes:

- `read_only_dry_run`
- `planned_only`
- `manual_approval`

Any step that mutates production, migrates a database, uploads raw data, mutates an index, or promotes a release must remain `planned_only` and `execution_approved=false`.

## Authorization Boundary

Phase 44 may authorize only Phase 45 execution planning.

The report must keep:

- `production_execution_authorized=false`
- `production_mutation_authorized=false`
- `database_migration_authorized=false`
- `raw_data_upload_authorized=false`
- `release_promotion_authorized=false`
- `lawyer_review_required=true`
- `no_final_legal_advice=true`

## Forbidden Content

Dry-run evidence must not contain:

- signing secrets;
- signed auth headers or body-hash headers;
- session cookies;
- bearer tokens;
- DB URLs;
- private keys;
- raw document bodies;
- raw response bodies;
- final legal advice language.

## Exit Criteria

- Local detached run returns `awaiting_production_cutover_readiness` until Phase 43 is ready.
- Dry-run planning cannot pass without Phase 43 readiness.
- Any execution approval, production mutation approval, DB migration approval, raw data upload, index mutation execution, release promotion execution, or forbidden content blocks.
- Rollback steps are complete, operator-owned, planned-only, and have expected evidence paths.
- Detached backend tests, frontend quality gate, Phase 44 gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, production mutation, release promotion, or raw data staging.
