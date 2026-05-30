# V2 Phase 40 Runbook: Hosted Dry-Run Evidence Capture

## Local Gate

Run:

```bash
scripts/run_detached_quality_gate.sh hosted-dry-run-evidence phase40-hosted-dry-run-evidence
```

The expected local status is `awaiting_hosted_environment_configuration`.

## Hosted Evidence Flow

First, run Phase 39 with hosted environment inspection:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/build_phase39_hosted_environment_config_pack.py \
  --include-environment \
  --output logs/readiness/phase39-hosted-environment-config-pack.json
```

Then run the Phase 38 hosted dry-run:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/run_phase38_hosted_capture_execution.py \
  --include-environment \
  --output logs/readiness/phase38-hosted-capture-execution.json
```

Then validate Phase 40:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/build_phase40_hosted_dry_run_evidence.py \
  --output logs/readiness/phase40-hosted-dry-run-evidence.json
```

The target hosted status is `hosted_dry_run_validated`.

## Review

Inspect:

```text
logs/readiness/phase40-hosted-dry-run-evidence.json
```

Confirm:

- Phase 39 status is `ready_for_hosted_capture_dry_run`;
- Phase 38 status is `ready_for_hosted_capture_execution`;
- Phase 38 has `execute=false`;
- Phase 38 has `environment_included=true`;
- captured evidence count is `0`;
- blockers count is `0`.

## Safety Checklist

- Do not commit `logs/`.
- Do not run Phase 38 with `--execute` during Phase 40.
- Do not paste signing headers, session cookies, bearer tokens, DB URLs, private keys, raw response bodies, raw document bodies, or raw data into evidence.
- If Phase 40 blocks, fix hosted dry-run evidence before moving to Phase 41.
