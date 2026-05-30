# V2 Phase 36 Contract: Hosted Evidence Capture Runner

## Purpose

Phase 36 provides the guarded runner that can gather the Phase 34 backend/DB staging evidence described by the Phase 35 capture plan.

The runner is dry-run by default. It performs real hosted HTTP checks only when run with both `--execute` and `--include-environment`.

## Implementation Surface

- Runner manifest: `rag/evals/phase36_hosted_evidence_capture_runner.json`
- Capture manifest: `rag/evals/phase35_hosted_evidence_capture.json`
- Runner script: `scripts/run_phase36_hosted_evidence_capture.py`
- Detached gate mode: `hosted-evidence-capture-runner`
- Report output: `logs/readiness/phase36-hosted-evidence-capture-run.json`

## Status Values

- `ready_for_hosted_capture_runner_configuration`: local prerequisites are present and the runner is safe for hosted configuration.
- `ready_for_hosted_capture_execution`: hosted environment validation is present, but the runner was not executed.
- `hosted_evidence_captured`: all capture tasks executed and wrote scrubbed Phase 34 evidence.
- `blocked`: prerequisites, environment validation, HTTP response shape, or capture output failed.

## Execution Rules

- Real capture requires `--execute --include-environment`.
- The runner uses only `GET` checks for hosted API smoke paths.
- Signed smoke checks may produce audit-event-only writes.
- Domain writes, migrations, cache creation, authority promotion, and raw data upload are prohibited.
- Response bodies are never written to logs.
- Logs may include route templates, HTTP status, JSON key names, missing key names, write classification, timestamps, and `exit_status`.

## Evidence Outputs

The runner writes Phase 34 evidence only under ignored `logs/` paths:

- `logs/hosted-staging/phase34-api-health.json`
- `logs/test-runs/phase34-platform-signed-workspace-smoke.log`
- `logs/test-runs/phase34-platform-authority-workflow.log`
- `logs/test-runs/phase34-platform-document-source-smoke.log`
- `logs/hosted-staging/phase34-db-readonly-health.json`
- `logs/hosted-staging/phase34-db-write-guard.json`
- `logs/hosted-staging/phase34-operator-db-acceptance.json`

## Safety Requirements

- Do not print or write `SL_LEGAL_AUTH_HMAC_SECRET`.
- Do not write signed cookies, session tokens, DB URLs, full hosted URLs, raw documents, raw response bodies, or raw `data/`.
- DB write guard evidence must report `write_count=0`, `migration_count=0`, and `raw_data_uploaded=false` before Phase 34 can validate.
- Evidence files remain untracked and must not be committed.

## Exit Criteria

- Local detached runner returns `ready_for_hosted_capture_runner_configuration`.
- Hosted dry-run can return `ready_for_hosted_capture_execution`.
- Hosted execution can return `hosted_evidence_captured`.
- Detached backend tests, frontend quality gate, Phase 36 runner gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
