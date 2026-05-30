# V2 Phase 45 Contract: Production Cutover Execution Plan

## Purpose

Phase 45 creates the reviewed production cutover execution plan.

This phase is not the production execution runner. It records required approvals, execution commands, rollback points, observation windows, and evidence handoff before any future production execution can be considered.

## Implementation Surface

- Manifest: `rag/evals/phase45_production_cutover_execution_plan.json`
- Execution-plan builder: `scripts/build_phase45_production_cutover_execution_plan.py`
- Detached gate mode: `production-cutover-execution-plan`
- Report output: `logs/readiness/phase45-production-cutover-execution-plan.json`

## Status Values

- `awaiting_production_cutover_dry_run`: Phase 44 has not returned `production_cutover_dry_run_planned`.
- `awaiting_execution_approvals`: Phase 44 dry-run planning is complete, but lawyer-owner, operator, or legal-review sign-off is missing.
- `production_cutover_execution_plan_ready`: dry-run evidence, approvals, command plan, rollback points, observation windows, and evidence handoff are complete.
- `blocked`: prerequisites failed, dry-run evidence failed, approvals failed, forbidden content was found, or execution-plan definitions are unsafe.

## Approval Gates

Phase 45 requires:

- lawyer-owner execution plan sign-off;
- operator execution plan sign-off;
- legal-review boundary sign-off.

Approval files must keep `production_execution_authorized=false`. They confirm review of the plan; they do not execute production.

## Command Rules

Every execution command must declare:

- stage;
- owner;
- command;
- expected evidence path;
- risk flags for production mutation, database migration, raw data upload, index mutation, and release promotion.

Commands that mutate production, promote a release, migrate a database, upload raw data, or mutate an index must also declare:

- an explicit execution flag;
- a rollback point;
- `execution_approved=false`.

## Authorization Boundary

Phase 45 does not authorize production execution.

The report must keep:

- `production_execution_authorized=false`
- `production_mutation_authorized=false`
- `database_migration_authorized=false`
- `raw_data_upload_authorized=false`
- `release_promotion_authorized=false`
- `phase46_monitoring_authorized=false`
- `lawyer_review_required=true`
- `no_final_legal_advice=true`

## Required Handoff

The execution plan must include handoff items for:

- Phase 44 release note;
- release provenance;
- signing plan;
- hosted staging acceptance;
- production validation evidence.

## Forbidden Content

Execution-plan evidence must not contain:

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

- Local detached run returns `awaiting_production_cutover_dry_run` until Phase 44 is planned.
- Execution planning cannot pass without Phase 44 dry-run evidence and required sign-offs.
- Any execution approval, production mutation approval, missing explicit execution flag, missing rollback point, incomplete observation window, incomplete evidence handoff, or forbidden content blocks.
- Detached backend tests, frontend quality gate, Phase 45 gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, production mutation, release promotion, or raw data staging.
