# V2 Phase 36 Runbook: Hosted Evidence Capture Runner

## Local Dry Run

Run Phase 35 first so the runner has its prerequisite report:

```bash
scripts/run_detached_quality_gate.sh hosted-evidence-capture-plan phase35-hosted-evidence-capture-plan
```

Then run the Phase 36 dry-run gate:

```bash
scripts/run_detached_quality_gate.sh hosted-evidence-capture-runner phase36-hosted-evidence-capture-runner
```

The expected local result is `ready_for_hosted_capture_runner_configuration`.

## Hosted Dry Run

Configure the same hosted staging variables required by Phase 35:

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

`SL_LEGAL_AUTH_HMAC_SECRET` must already be configured securely.

Run a hosted dry run:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/run_phase36_hosted_evidence_capture.py \
  --include-environment \
  --output logs/readiness/phase36-hosted-evidence-capture-run.json
```

The expected status is `ready_for_hosted_capture_execution`.

## Hosted Capture

Run capture only after the dry-run is clean:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/run_phase36_hosted_evidence_capture.py \
  --include-environment \
  --execute \
  --output logs/readiness/phase36-hosted-evidence-capture-run.json
```

The expected status is `hosted_evidence_captured`.

## Evidence Review

After hosted capture, rerun Phase 34:

```bash
scripts/run_detached_quality_gate.sh backend-db-staging-validation phase34-backend-db-staging-validation
```

The target status is `backend_db_staging_validated`.

## Safety Checklist

- Keep all generated evidence under `logs/`.
- Do not commit generated logs or hosted evidence.
- Do not paste secrets, signed cookies, DB URLs, full hosted URLs, raw document bodies, or raw `data/` content into evidence files.
- Confirm signed smoke checks are only audit-event writes.
- Confirm no migration, authority promotion, document caching, raw data upload, or domain-data mutation occurred.
