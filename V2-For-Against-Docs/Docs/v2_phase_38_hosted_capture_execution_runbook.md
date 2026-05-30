# V2 Phase 38 Runbook: Hosted Capture Execution Orchestrator

## Local Gate

Run the dry local orchestrator:

```bash
scripts/run_detached_quality_gate.sh hosted-capture-execution phase38-hosted-capture-execution
```

The expected local status is `awaiting_hosted_capture_configuration`.

## Hosted Dry-Run

Configure the hosted staging environment variables required by Phase 35:

```text
SL_LEGAL_STAGING_API_BASE_URL
SL_LEGAL_STAGING_USER_ID
SL_LEGAL_AUTH_HMAC_SECRET
SL_LEGAL_STAGING_CASE_ID
SL_LEGAL_STAGING_DOCUMENT_ID
SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED=true
SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT=0
SL_LEGAL_PHASE35_DB_MIGRATION_COUNT=0
SL_LEGAL_PHASE35_RAW_DATA_UPLOADED=false
```

Then run:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/run_phase38_hosted_capture_execution.py \
  --include-environment \
  --output logs/readiness/phase38-hosted-capture-execution.json
```

The expected hosted dry-run status is `ready_for_hosted_capture_execution`.

## Hosted Execution

After the hosted dry-run is clean, execute capture:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/run_phase38_hosted_capture_execution.py \
  --include-environment \
  --execute \
  --output logs/readiness/phase38-hosted-capture-execution.json
```

Phase 38 refreshes Phase 35, Phase 36, Phase 34, and Phase 37 readiness reports in sequence.

## Result Review

Inspect:

```text
logs/readiness/phase38-hosted-capture-execution.json
```

The ideal hosted result is `hosted_capture_execution_accepted`.

Acceptable intermediate hosted results:

- `hosted_capture_executed_pending_backend_db_validation`
- `hosted_capture_executed_pending_acceptance`

These mean capture ran, but the downstream evidence state still needs review.

## Safety Checklist

- Do not commit `logs/`.
- Do not paste secret values, signing headers, cookies, DB URLs, raw response bodies, raw document bodies, or raw data into reports.
- If execution returns `blocked`, review the nested Phase 35, Phase 36, Phase 34, and Phase 37 sections before rerunning.
- If forbidden content is detected by Phase 37, regenerate the hosted evidence from the source instead of editing around it locally.
- Keep all DB checks read-only except the explicitly allowed signed API smoke checks classified as `audit_event_only`.
