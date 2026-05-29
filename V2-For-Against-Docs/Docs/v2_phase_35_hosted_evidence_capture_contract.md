# V2 Phase 35 Contract: Hosted Evidence Capture Plan

## Purpose

Phase 35 turns the Phase 34 backend/DB staging evidence requirements into a repeatable hosted capture plan. It validates prerequisites, checks required staging environment variables without printing secret values, and defines which smoke checks are allowed to create audit-event-only writes.

This phase does not upload raw data, migrate the database, write Phase 34 evidence from local execution, or commit hosted logs.

## Implementation Surface

- Manifest: `rag/evals/phase35_hosted_evidence_capture.json`
- Report builder: `scripts/build_phase35_hosted_evidence_capture_plan.py`
- Detached gate mode: `hosted-evidence-capture-plan`
- Report output: `logs/readiness/phase35-hosted-evidence-capture-plan.json`

## Status Values

- `ready_for_hosted_capture_configuration`: local prerequisites are present and the hosted environment still needs operator configuration.
- `ready_for_capture_execution`: required hosted variables and DB operator confirmations are present.
- `blocked`: a prerequisite is missing, an environment requirement is invalid, or a DB-writing capture task lacks an allowed write classification.

## Required Environment

Hosted capture execution requires:

- `SL_LEGAL_STAGING_API_BASE_URL`
- `SL_LEGAL_STAGING_USER_ID`
- `SL_LEGAL_AUTH_HMAC_SECRET`
- `SL_LEGAL_STAGING_CASE_ID`
- `SL_LEGAL_STAGING_DOCUMENT_ID`
- `SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED=true`
- `SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT=0`
- `SL_LEGAL_PHASE35_DB_MIGRATION_COUNT=0`
- `SL_LEGAL_PHASE35_RAW_DATA_UPLOADED=false`

Secret values are checked for presence and minimum length only. They must not be printed into reports or logs.

## Capture Task Rules

- `/health` capture is a read-only HTTP check.
- Signed workspace, authority workflow, and document-source status smoke checks may create audit events only.
- Any capture task with DB write potential must declare `write_classification=audit_event_only`.
- Operator DB evidence remains JSON under ignored `logs/hosted-staging/`.
- Detached smoke logs remain under ignored `logs/test-runs/`.
- Capture output must not contain signed cookies, HMAC secrets, DB URLs, raw data, or document bodies.

## Exit Criteria

- Local run returns `ready_for_hosted_capture_configuration`.
- Hosted configuration run returns `ready_for_capture_execution`.
- Capture plan exposes every Phase 34 evidence file that still needs hosted data.
- DB write classification prevents uncontrolled write-path smoke checks.
- Detached backend tests, frontend quality gate, Phase 35 gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
