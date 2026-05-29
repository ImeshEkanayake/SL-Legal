# V2 Phase 35 Runbook: Hosted Evidence Capture Plan

## Local Gate

Run Phase 34 first:

```bash
scripts/run_detached_quality_gate.sh backend-db-staging-validation phase34-backend-db-staging-validation
```

Then run Phase 35:

```bash
scripts/run_detached_quality_gate.sh hosted-evidence-capture-plan phase35-hosted-evidence-capture-plan
```

The expected local result is `ready_for_hosted_capture_configuration`.

## Hosted Configuration Check

In hosted staging, provide environment values through the deployment platform or a secure shell session:

```bash
export SL_LEGAL_STAGING_API_BASE_URL="https://staging-api.example"
export SL_LEGAL_STAGING_USER_ID="reviewer@example"
export SL_LEGAL_STAGING_CASE_ID="case-id"
export SL_LEGAL_STAGING_DOCUMENT_ID="document-id"
export SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED="true"
export SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT="0"
export SL_LEGAL_PHASE35_DB_MIGRATION_COUNT="0"
export SL_LEGAL_PHASE35_RAW_DATA_UPLOADED="false"
```

`SL_LEGAL_AUTH_HMAC_SECRET` must already be configured securely in the hosted environment.

Then run:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/build_phase35_hosted_evidence_capture_plan.py \
  --include-environment \
  --output logs/readiness/phase35-hosted-evidence-capture-plan.json
```

The expected hosted configuration result is `ready_for_capture_execution`.

## Evidence Capture Boundaries

Write evidence only under ignored paths:

```text
logs/hosted-staging/
logs/test-runs/
logs/readiness/
```

Do not commit evidence logs. Do not paste secrets, signed cookies, DB URLs, raw document bodies, or raw `data/` content into evidence files.

## Phase 34 Evidence Outputs

The capture plan covers these Phase 34 outputs:

```text
logs/hosted-staging/phase34-api-health.json
logs/test-runs/phase34-platform-signed-workspace-smoke.log
logs/test-runs/phase34-platform-authority-workflow.log
logs/test-runs/phase34-platform-document-source-smoke.log
logs/hosted-staging/phase34-db-readonly-health.json
logs/hosted-staging/phase34-db-write-guard.json
logs/hosted-staging/phase34-operator-db-acceptance.json
```

Signed workspace and document-source checks may write audit events. They must not create, modify, promote, cache, migrate, upload, or delete matter data.

## After Capture

After hosted evidence is attached, rerun Phase 34:

```bash
scripts/run_detached_quality_gate.sh backend-db-staging-validation phase34-backend-db-staging-validation
```

The target status is `backend_db_staging_validated`.

If the report blocks, inspect:

```text
logs/readiness/phase34-backend-db-staging-validation.json
logs/readiness/phase35-hosted-evidence-capture-plan.json
```
