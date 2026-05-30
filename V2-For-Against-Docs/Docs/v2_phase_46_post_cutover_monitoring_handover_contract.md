# V2 Phase 46 Contract: Post-Cutover Monitoring and Operational Handover

## Purpose

Phase 46 validates post-cutover monitoring and handover evidence after a reviewed production cutover has already been approved and executed.

This phase does not execute production. It determines whether production can be treated as operationally handed over after the monitoring window, rollback readiness review, incident-response review, and data-update boundary review are attached.

## Implementation Surface

- Manifest: `rag/evals/phase46_post_cutover_monitoring_handover.json`
- Handover builder: `scripts/build_phase46_post_cutover_monitoring_handover.py`
- Detached gate mode: `post-cutover-monitoring-handover`
- Report output: `logs/readiness/phase46-post-cutover-monitoring-handover.json`
- Handover document: `Docs/v2_phase_46_operational_handover.md`

## Status Values

- `awaiting_production_cutover_execution_plan`: Phase 45 has not returned `production_cutover_execution_plan_ready`.
- `awaiting_cutover_execution_evidence`: Phase 45 is ready, but reviewed cutover execution evidence is missing.
- `awaiting_monitoring_evidence`: cutover execution evidence is present, but monitoring windows are incomplete.
- `awaiting_operational_handover`: monitoring evidence is present, but rollback, incident-response, data-update, or handover evidence is incomplete.
- `post_cutover_operational_handover_ready`: all required post-cutover monitoring and handover evidence is present and valid.
- `blocked`: prerequisites failed, evidence failed, definitions are unsafe, or forbidden content was found.

## Monitoring Requirements

Phase 46 requires evidence for:

- API health.
- Retrieval latency.
- Source viewer latency.
- Citation validation failures.
- Review queue latency.
- Application error rates.

Each dashboard check must name a metric, owner, target, severity, and linked monitoring evidence item.

## Handover Requirements

Phase 46 requires:

- reviewed production cutover execution record;
- signed smoke verification record;
- rollback readiness review;
- incident-response readiness review;
- data update and Git release separation review;
- support handover;
- legal-review handover;
- data update handover;
- future corpus growth handover.

## Authorization Boundary

Phase 46 does not authorize production execution.

The report must keep:

- `production_execution_authorized=false`
- `production_mutation_authorized=false`
- `database_migration_authorized=false`
- `raw_data_upload_authorized=false`
- `release_promotion_authorized=false`
- `lawyer_review_required=true`
- `no_final_legal_advice=true`

The report may set `production_operational_complete=true` only when the status is `post_cutover_operational_handover_ready`.

## Data Boundary

Raw data upload remains outside the Git code release process. Data updates, corpus growth, object-storage decisions, release artifacts, manifests, and hydration scripts require a separate reviewed data plan.

## Forbidden Content

Post-cutover evidence must not contain:

- signed auth headers or body-hash headers;
- session cookies;
- bearer tokens;
- DB URLs;
- private keys;
- raw document bodies;
- raw response bodies;
- final legal advice language.

## Exit Criteria

- Local detached run returns `awaiting_production_cutover_execution_plan` until Phase 45 is ready.
- Operational handover cannot pass without cutover execution evidence, monitoring evidence, rollback and incident-response review, data-update separation review, and handover documentation.
- Any production authorization by Phase 46, DB migration authorization, raw data upload authorization, forbidden content, unknown dashboard evidence link, or incomplete incident template blocks.
- Detached backend tests, frontend quality gate, Phase 46 gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, unmanaged production mutation, release promotion, or raw data staging.
