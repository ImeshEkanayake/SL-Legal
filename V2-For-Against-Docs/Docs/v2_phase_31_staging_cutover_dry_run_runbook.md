# V2 Phase 31 Runbook: Staging Cutover Dry Run

## Local Dry Run

Generate Phase 30 local readiness first:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness phase30-ui-deployment-readiness
```

Then generate the Phase 31 dry-run report:

```bash
scripts/run_detached_quality_gate.sh staging-cutover-dry-run phase31-staging-cutover-dry-run
```

Expected local result:

- `exit_status=0`
- report status `ready_for_hosted_env_setup`

This means the code release and local evidence are ready, but real hosted staging variables still need deployment-console configuration.

## Hosted Staging Dry Run

In the staging platform, configure:

- `SL_LEGAL_API_BASE_URL`
- `SL_LEGAL_AUTH_HMAC_SECRET`
- `SL_LEGAL_UI_SESSION_SECRET`
- optional `SL_LEGAL_UI_SESSION_COOKIE_NAME`

Do not configure `SL_LEGAL_UI_USER_ID` in staging.

Run:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness-env phase31-staging-env-readiness
scripts/run_detached_quality_gate.sh staging-cutover-dry-run phase31-staging-cutover-dry-run
```

Expected hosted result:

- `phase31-staging-env-readiness.log` exits `0`
- Phase 31 report status `ready_for_staging_cutover`
- no secret values appear in logs or JSON reports

## Required Smoke Checks Before Cutover

Run these detached checks before exposing staging to lawyer review:

```bash
scripts/run_detached_quality_gate.sh phase29-browser-workflow phase31-staging-browser-smoke
scripts/run_detached_quality_gate.sh tests phase31-staging-tests
scripts/run_detached_quality_gate.sh frontend phase31-staging-frontend
```

Keep the logs under `logs/test-runs` as local evidence. Do not upload raw corpus data.

## Rollback

If any smoke check fails:

- Restore the previous stable UI deployment or previous platform deployment alias.
- Disable staging route exposure or revoke the staging session cookie.
- Preserve detached logs, readiness reports, and browser screenshots for diagnosis.
- Do not mutate the shared database to recover from a UI cutover failure.

## Approval

Before staging cutover:

- Operator confirms hosted secrets are present only in the deployment platform.
- Lawyer owner accepts the staging smoke output.
- Engineering confirms no V1 changes, raw data upload, or database migration occurred.
