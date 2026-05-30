# V2 Phase 40 Contract: Hosted Dry-Run Evidence Capture

## Purpose

Phase 40 validates the hosted Phase 38 dry-run evidence before any hosted capture execution is allowed.

This phase does not execute hosted capture. It accepts only evidence that Phase 38 was run with hosted environment inspection enabled, without `--execute`, and without captured evidence.

## Implementation Surface

- Manifest: `rag/evals/phase40_hosted_dry_run_evidence.json`
- Dry-run evidence builder: `scripts/build_phase40_hosted_dry_run_evidence.py`
- Detached gate mode: `hosted-dry-run-evidence`
- Report output: `logs/readiness/phase40-hosted-dry-run-evidence.json`

## Status Values

- `awaiting_hosted_environment_configuration`: Phase 39 is not yet `ready_for_hosted_capture_dry_run`.
- `awaiting_hosted_dry_run_evidence`: Phase 39 is ready, but Phase 38 dry-run evidence is missing or not yet `ready_for_hosted_capture_execution`.
- `hosted_dry_run_validated`: Phase 39 is ready, Phase 38 dry-run is ready for execution, no capture ran, and the evidence is scrubbed.
- `blocked`: prerequisites failed, dry-run evidence failed validation, or forbidden hosted content was found.

## Evidence Boundary

Phase 40 validates:

- `logs/readiness/phase39-hosted-environment-config-pack.json`
- `logs/readiness/phase38-hosted-capture-execution.json`

The Phase 38 dry-run report must show:

- `execute=false`
- `environment_included=true`
- `summary.phase35_status=ready_for_capture_execution`
- `summary.phase36_status=ready_for_hosted_capture_execution`
- `summary.captured_evidence=0`
- `summary.blockers=0`

## Forbidden Content

Dry-run evidence must not contain:

- signed auth headers or body-hash headers;
- session cookies;
- bearer tokens;
- DB URLs;
- private keys;
- raw document bodies;
- raw response bodies.

## Exit Criteria

- Local detached run returns `awaiting_hosted_environment_configuration`.
- Hosted validation returns `hosted_dry_run_validated` only after Phase 39 and Phase 38 dry-run evidence pass.
- Failed or incomplete evidence blocks hosted capture execution.
- Detached backend tests, frontend quality gate, Phase 40 gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
