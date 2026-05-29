# V2 Phase 32 Contract: Hosted Staging Execution Pack

## Purpose

Phase 32 prepares V2 for real hosted staging execution without performing the deployment from the local workspace.

The phase produces an operator-safe execution pack that consumes Phase 31 cutover evidence, lists the hosted-only execution steps, provides a signed UI session token utility for private lawyer review, and keeps rollback steps explicit.

## Scope

Included:

- Hosted staging execution manifest at `rag/evals/phase32_hosted_staging_execution.json`.
- Execution-pack builder at `scripts/build_phase32_hosted_staging_execution_pack.py`.
- Detached gate mode `hosted-staging-execution-pack`.
- Private UI session token utility at `scripts/create_ui_session_token.py`.
- Tests for execution-pack states, blockers, CLI output, and token shape.

Excluded:

- V1 changes.
- Raw data upload.
- Database migration or database writes.
- Actual hosted deployment execution from the local workspace.
- Printing hosted secret values in reports.
- Committing staging session tokens.

## Statuses

`ready_for_hosted_configuration` means the local Phase 31 dry run is accepted, but hosted staging still needs deployment-platform environment configuration and hosted env validation.

`ready_for_hosted_staging_execution` means Phase 31 has been regenerated with hosted environment validation and returned `ready_for_staging_cutover`.

`blocked` means required reports are missing or failed, execution steps are incomplete, rollback steps are incomplete, or required manual approvals are malformed.

## Required Inputs

The execution pack requires:

- `logs/readiness/phase31-staging-cutover-dry-run.json`
- `rag/evals/phase31_staging_cutover_dry_run.json`
- `Docs/v2_phase_31_staging_cutover_dry_run_contract.md`
- `Docs/v2_phase_31_staging_cutover_dry_run_runbook.md`
- `Docs/releases/v2_phase_31_staging_cutover_dry_run.md`

The Phase 31 report must have status `ready_for_hosted_env_setup` or `ready_for_staging_cutover`.

## Hosted Execution Steps

1. Configure hosted staging environment variables in the deployment platform.
2. Run `ui-deployment-readiness-env` in hosted staging.
3. Rebuild the Phase 31 cutover dry-run report.
4. Create a private signed UI session cookie for the reviewer.
5. Run browser smoke and regression gates.
6. Record lawyer-owner staging acceptance.

## Session Token Utility

The utility reads `SL_LEGAL_UI_SESSION_SECRET` or `SL_LEGAL_AUTH_HMAC_SECRET` from the execution environment:

```bash
python3 scripts/create_ui_session_token.py \
  --user-id reviewer@example.com \
  --output cookie
```

The output token is sensitive. It must be copied only into a private staging review browser session and must never be committed or pasted into issue trackers.

## Acceptance Criteria

- Execution pack returns at least `ready_for_hosted_configuration` locally.
- Hosted execution pack can return `ready_for_hosted_staging_execution` only after Phase 31 is `ready_for_staging_cutover`.
- Session-token CLI enforces 32+ character secrets, valid user ids, and 60+ second TTLs.
- Reports contain commands and evidence paths but not secret values or generated tokens.
- Detached backend tests, frontend quality gate, Phase 32 execution-pack gate, secret scan, and marker scan pass.
