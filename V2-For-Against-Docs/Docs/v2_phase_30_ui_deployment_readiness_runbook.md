# V2 Phase 30 Runbook: UI Deployment Readiness

## Before Running

Confirm Phase 29 browser validation has been run in the same workspace:

```bash
scripts/run_detached_quality_gate.sh phase29-browser-workflow phase29-browser-workflow-validation
```

The Phase 30 gate reads `logs/test-runs/phase29-browser-workflow-validation.log` and expects `exit_status=0`.

## Local Readiness

Run:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness phase30-ui-deployment-readiness
```

Inspect:

```bash
tail -n 80 logs/test-runs/phase30-ui-deployment-readiness.log
```

Expected result:

- `exit_status=0`
- report status `ready_for_hosted_env_review`

This status is correct for local Git work because hosted secrets are not loaded into the workspace.

## Hosted Environment Review

From the staging or production runtime shell, set the real deployment variables in the platform console and run:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness-env phase30-ui-deployment-readiness-env
```

Expected result:

- `exit_status=0`
- report status `ready_for_deployment_review`
- no secret values in the report
- `SL_LEGAL_UI_USER_ID` absent in staging/production

## If Blocked

For missing evidence:

- Re-run Phase 29 browser workflow validation.
- Confirm `web/package.json` still contains `phase29:e2e`.
- Confirm `scripts/run_detached_quality_gate.sh` still contains `phase29-browser-workflow`.

For hosted environment blockers:

- Add or correct `SL_LEGAL_API_BASE_URL`.
- Add 32+ character values for `SL_LEGAL_AUTH_HMAC_SECRET` and `SL_LEGAL_UI_SESSION_SECRET`.
- Remove `SL_LEGAL_UI_USER_ID` from staging/production.
- Re-run the hosted environment review gate.

## Release Boundary

Do not upload raw corpus data during this phase.
Do not migrate or mutate the database during this phase.
Do not treat `ready_for_hosted_env_review` as production approval; it means the next step is deployment-console review.

