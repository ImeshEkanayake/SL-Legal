# V2 Phase 38 Contract: Hosted Capture Execution Orchestrator

## Purpose

Phase 38 runs the hosted evidence chain as one controlled staging workflow:

1. Build the Phase 35 hosted environment preflight.
2. Run the Phase 36 hosted evidence capture runner.
3. Rebuild the Phase 34 backend and DB staging validation report.
4. Rebuild the Phase 37 hosted capture acceptance report.

The orchestrator is dry-run by default. Real hosted calls require both `--execute` and `--include-environment`.

## Implementation Surface

- Manifest: `rag/evals/phase38_hosted_capture_execution.json`
- Orchestrator: `scripts/run_phase38_hosted_capture_execution.py`
- Detached gate mode: `hosted-capture-execution`
- Report output: `logs/readiness/phase38-hosted-capture-execution.json`

The orchestrator also refreshes these ignored readiness reports:

- `logs/readiness/phase35-hosted-evidence-capture-plan.json`
- `logs/readiness/phase36-hosted-evidence-capture-run.json`
- `logs/readiness/phase34-backend-db-staging-validation.json`
- `logs/readiness/phase37-hosted-capture-acceptance.json`

## Status Values

- `awaiting_hosted_capture_configuration`: hosted environment values were not supplied, or the dry-run is waiting for hosted configuration.
- `ready_for_hosted_capture_execution`: hosted environment values were supplied and validated, but `--execute` was not supplied.
- `hosted_capture_executed_pending_backend_db_validation`: Phase 36 captured evidence, but Phase 34 has not yet reached `backend_db_staging_validated`.
- `hosted_capture_executed_pending_acceptance`: Phase 36 captured evidence and Phase 34 validated it, but Phase 37 has not yet accepted the capture.
- `hosted_capture_execution_accepted`: Phase 36 captured evidence, Phase 34 validated it, and Phase 37 accepted it.
- `blocked`: prerequisites failed, environment validation failed during execution, capture failed, downstream validation blocked, or acceptance blocked.

## Execution Rules

- Local detached mode does not inspect hosted secrets and does not execute hosted HTTP calls.
- Hosted execution requires `--execute --include-environment`.
- The only DB-writing HTTP checks allowed in this phase are Phase 36 signed smoke checks classified as `audit_event_only`.
- The orchestrator must not print secret values, signed headers, session cookies, DB URLs, raw response bodies, raw document bodies, or raw `data/` content.
- Evidence remains under ignored `logs/` paths and must not be committed.

## Exit Criteria

- Local detached run returns `awaiting_hosted_capture_configuration`.
- Hosted dry-run with environment returns `ready_for_hosted_capture_execution`.
- Hosted execution can only advance after Phase 36 reports `hosted_evidence_captured`.
- Final accepted hosted execution requires Phase 34 `backend_db_staging_validated` and Phase 37 `hosted_capture_accepted`.
- Detached backend tests, frontend quality gate, Phase 38 execution gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
