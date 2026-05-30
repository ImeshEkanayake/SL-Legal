# V2 Phase 39 Contract: Hosted Environment Configuration Pack

## Purpose

Phase 39 makes the hosted staging configuration required for Phase 38 explicit, reviewable, and repeatable before any real hosted dry-run or capture execution is attempted.

This phase does not execute hosted capture. It checks the configuration boundary, command recipes, and expected evidence outputs.

## Implementation Surface

- Manifest: `rag/evals/phase39_hosted_environment_config.json`
- Config pack builder: `scripts/build_phase39_hosted_environment_config_pack.py`
- Detached gate mode: `hosted-environment-config-pack`
- Report output: `logs/readiness/phase39-hosted-environment-config-pack.json`

## Status Values

- `awaiting_hosted_environment_configuration`: local run did not inspect hosted environment values.
- `ready_for_hosted_capture_dry_run`: hosted environment values were inspected and match the Phase 35 requirements.
- `blocked`: prerequisites are missing, environment checks fail, command recipes are unsafe, evidence outputs are invalid, or Phase 39 environment requirements drift from Phase 35.

## Safety Boundary

Phase 39 may check:

- whether environment values are present;
- whether URL values have valid schemes;
- whether secret values meet minimum length;
- whether operator confirmations match expected values.

Phase 39 must not print or persist actual secret values, signed headers, session cookies, DB URLs, raw response bodies, raw document bodies, or raw data.

## Exit Criteria

- Local detached run returns `awaiting_hosted_environment_configuration`.
- Hosted run with `--include-environment` returns `ready_for_hosted_capture_dry_run`.
- Command recipes include a hosted dry-run and a hosted execution path.
- Hosted execution command recipe includes both `--execute` and `--include-environment`.
- Evidence outputs are all non-committable ignored `logs/` paths.
- Detached backend tests, frontend quality gate, Phase 39 config gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
