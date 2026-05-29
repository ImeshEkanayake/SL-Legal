# V2 Phase 32 Runbook: Hosted Staging Execution Pack

## Local Execution Pack

Generate Phase 31 evidence first:

```bash
scripts/run_detached_quality_gate.sh staging-cutover-dry-run phase31-staging-cutover-dry-run
```

Then generate the Phase 32 execution pack:

```bash
scripts/run_detached_quality_gate.sh hosted-staging-execution-pack phase32-hosted-staging-execution-pack
```

Expected local result:

- `exit_status=0`
- report status `ready_for_hosted_configuration`

This means local release evidence is ready, but actual hosted staging execution still requires platform environment setup.

## Hosted Staging Execution

In the staging platform, configure:

- `SL_LEGAL_API_BASE_URL`
- `SL_LEGAL_AUTH_HMAC_SECRET`
- `SL_LEGAL_UI_SESSION_SECRET`
- optional `SL_LEGAL_UI_SESSION_COOKIE_NAME`

Do not configure `SL_LEGAL_UI_USER_ID` in staging.

Run:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness-env phase32-hosted-env-readiness
scripts/run_detached_quality_gate.sh staging-cutover-dry-run phase32-hosted-cutover-dry-run
scripts/run_detached_quality_gate.sh hosted-staging-execution-pack phase32-hosted-staging-execution-pack
```

Expected hosted result:

- hosted env readiness exits `0`
- Phase 31 report returns `ready_for_staging_cutover`
- Phase 32 report returns `ready_for_hosted_staging_execution`

## Reviewer Session Cookie

Create a private signed reviewer cookie inside the hosted/staging execution environment:

```bash
python3 scripts/create_ui_session_token.py \
  --user-id reviewer@example.com \
  --ttl-seconds 28800 \
  --output cookie
```

Copy the cookie into a private browser session for staging review. Do not commit the token, save it in Git, or paste it into shared notes.

## Smoke Checks

Before exposing staging for lawyer review, run:

```bash
scripts/run_detached_quality_gate.sh phase29-browser-workflow phase32-hosted-browser-smoke
scripts/run_detached_quality_gate.sh tests phase32-hosted-tests
scripts/run_detached_quality_gate.sh frontend phase32-hosted-frontend
```

Keep detached logs local as execution evidence. Do not upload raw corpus data.

## Rollback

If hosted staging fails:

- Revoke or expire the staging review session by rotating `SL_LEGAL_UI_SESSION_SECRET`.
- Restore the previous staging deployment alias.
- Preserve detached logs and readiness reports locally for diagnosis.
- Do not mutate the shared database to recover from UI deployment failure.
