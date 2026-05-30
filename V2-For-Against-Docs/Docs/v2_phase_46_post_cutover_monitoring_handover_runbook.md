# V2 Phase 46 Runbook: Post-Cutover Monitoring and Operational Handover

## Purpose

Use this runbook after Phase 45 has produced a reviewed production cutover execution plan and the approved cutover has been executed.

Phase 46 validates monitoring and handover evidence. It does not execute deployment commands, mutate databases, upload raw data, or promote releases.

## Inputs

Required committed inputs:

- `rag/evals/phase46_post_cutover_monitoring_handover.json`
- `Docs/v2_phase_46_post_cutover_monitoring_handover_contract.md`
- `Docs/v2_phase_46_operational_handover.md`
- Phase 45 manifest, contract, runbook, release note, and builder

Required ignored evidence:

- `logs/readiness/phase45-production-cutover-execution-plan.json`
- `logs/production-cutover/phase46-cutover-execution-record.json`
- `logs/production-cutover/phase46-signed-smoke-record.json`
- `logs/production-cutover/phase46-api-health-monitoring.json`
- `logs/production-cutover/phase46-retrieval-latency-monitoring.json`
- `logs/production-cutover/phase46-source-viewer-latency-monitoring.json`
- `logs/production-cutover/phase46-citation-validation-monitoring.json`
- `logs/production-cutover/phase46-review-queue-latency-monitoring.json`
- `logs/production-cutover/phase46-error-rate-monitoring.json`
- `logs/production-cutover/phase46-rollback-readiness-review.json`
- `logs/production-cutover/phase46-incident-response-review.json`
- `logs/production-cutover/phase46-data-update-separation-review.json`

## Local Gate

Run the detached gate:

```bash
scripts/run_detached_quality_gate.sh post-cutover-monitoring-handover phase46-post-cutover-monitoring-handover
```

Expected local status before Phase 45 is ready:

```text
awaiting_production_cutover_execution_plan
```

## Evidence Shape

Cutover execution record:

```json
{
  "status": "production_cutover_executed",
  "reviewed_phase45_execution_plan": true,
  "executed_under_phase45_approval": true,
  "rollback_available": true,
  "database_migration_authorized": false,
  "raw_data_upload_authorized": false,
  "lawyer_review_required": true,
  "no_final_legal_advice": true
}
```

Data update separation review:

```json
{
  "status": "accepted",
  "data_updates_separate_from_git": true,
  "raw_data_upload_authorized": false,
  "database_migration_authorized": false,
  "corpus_growth_requires_separate_plan": true
}
```

## Decision Interpretation

- `awaiting_production_cutover_execution_plan`: finish Phase 45 first.
- `awaiting_cutover_execution_evidence`: attach reviewed cutover execution and signed smoke records.
- `awaiting_monitoring_evidence`: attach all monitoring-window evidence.
- `awaiting_operational_handover`: attach rollback, incident-response, data-update, and handover evidence.
- `post_cutover_operational_handover_ready`: production operation is ready for handover review.
- `blocked`: inspect `blockers`, repair evidence or manifest definitions, and rerun Phase 46.

## Safety Rules

- Do not commit ignored `logs/` evidence.
- Do not upload raw `data/`.
- Do not expose secret values in evidence or release notes.
- Do not apply a database migration.
- Do not execute deployment commands from this phase.
- Do not promote a release from this phase.
- Keep data update procedures separate from Git code release procedures.
- Do not change V1.
- Do not describe any generated report as final legal advice.
