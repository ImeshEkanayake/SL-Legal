# V2 Phase 39 Runbook: Hosted Environment Configuration Pack

## Local Gate

Run:

```bash
scripts/run_detached_quality_gate.sh hosted-environment-config-pack phase39-hosted-environment-config-pack
```

The expected local status is `awaiting_hosted_environment_configuration`.

## Hosted Configuration Check

Set the hosted staging variables:

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
PYTHONPATH=rag uv run --with pydantic python scripts/build_phase39_hosted_environment_config_pack.py \
  --include-environment \
  --output logs/readiness/phase39-hosted-environment-config-pack.json
```

The expected hosted status is `ready_for_hosted_capture_dry_run`.

## Next Hosted Commands

After Phase 39 is ready, run the Phase 38 hosted dry-run:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/run_phase38_hosted_capture_execution.py \
  --include-environment \
  --output logs/readiness/phase38-hosted-capture-execution.json
```

Only after the dry-run is clean, run hosted capture execution:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/run_phase38_hosted_capture_execution.py \
  --include-environment \
  --execute \
  --output logs/readiness/phase38-hosted-capture-execution.json
```

## Review

Inspect:

```text
logs/readiness/phase39-hosted-environment-config-pack.json
```

Check:

- environment checks are verified;
- command recipes are present;
- evidence outputs are under ignored `logs/` paths;
- no blockers are present.

## Safety Checklist

- Do not commit `logs/`.
- Do not paste secret values, signed headers, session cookies, DB URLs, raw response bodies, raw document bodies, or raw data into any report.
- Keep DB confirmations at read-only, zero domain writes, zero migrations, and no raw data upload.
- If Phase 39 blocks, fix the hosted configuration before running Phase 38.
