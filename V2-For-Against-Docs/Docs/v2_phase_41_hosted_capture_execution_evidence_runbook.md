# V2 Phase 41 Runbook: Hosted Capture Execution Evidence

## Local Gate

Run:

```bash
scripts/run_detached_quality_gate.sh hosted-capture-execution-evidence phase41-hosted-capture-execution-evidence
```

The expected local status is `awaiting_hosted_dry_run_validation`.

## Hosted Evidence Flow

Run Phase 40 first and confirm:

```text
logs/readiness/phase40-hosted-dry-run-evidence.json
```

has status `hosted_dry_run_validated`.

Then execute hosted capture through Phase 38:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/run_phase38_hosted_capture_execution.py \
  --include-environment \
  --execute \
  --output logs/readiness/phase38-hosted-capture-execution.json
```

Then run Phase 41:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/build_phase41_hosted_capture_execution_evidence.py \
  --output logs/readiness/phase41-hosted-capture-execution-evidence.json
```

## Review

Inspect:

```text
logs/readiness/phase41-hosted-capture-execution-evidence.json
```

Expected progress states:

- `hosted_capture_executed_pending_backend_db_validation`
- `hosted_capture_executed_pending_acceptance`
- `hosted_capture_execution_evidence_validated`

The final target is `hosted_capture_execution_evidence_validated`.

## Safety Checklist

- Do not commit `logs/`.
- Confirm Phase 38 used `--execute --include-environment`.
- Confirm Phase 36 captured all seven evidence items.
- Confirm DB write guard reports `write_count=0`, `migration_count=0`, and `raw_data_uploaded=false`.
- Confirm Phase 37 does not find forbidden content.
- Do not paste signing secrets, signed headers, session cookies, bearer tokens, DB URLs, private keys, raw response bodies, raw document bodies, or raw data into evidence.
- If Phase 41 blocks, regenerate hosted evidence from the source rather than editing around the issue locally.
