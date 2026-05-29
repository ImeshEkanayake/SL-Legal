# V2 Phase 30 Contract: UI Deployment Readiness

## Purpose

Phase 30 turns the completed browser workflow validation into a repeatable deployment-readiness decision for the V2 lawyer workspace UI.

The phase does not deploy the system. It checks that the latest UI workflow evidence exists, that the browser validation path remains wired into the detached gate runner, and that hosted environment variables can be reviewed without exposing secret values.

## Scope

Included:

- Readiness manifest at `rag/evals/phase30_ui_deployment_readiness.json`.
- Readiness report builder at `scripts/build_phase30_ui_deployment_readiness.py`.
- Detached gate mode `ui-deployment-readiness`.
- Optional hosted environment gate mode `ui-deployment-readiness-env`.
- Unit tests for manifest loading, evidence checks, secret-safe environment checks, and CLI output.

Excluded:

- V1 changes.
- Raw data upload.
- Database migration or database writes.
- Production deployment execution.
- Printing hosted secret values into logs.

## Readiness Statuses

`ready_for_hosted_env_review` means local release evidence is present and passing, but hosted deployment variables were not inspected in the current process.

`ready_for_deployment_review` means local release evidence is present and the current process environment contains valid hosted values for the required UI variables.

`blocked` means required evidence is missing, a detached run did not exit with status 0, a script/gate is not wired as expected, a required hosted environment variable is missing or invalid, or a development-only UI user id is present in staging/production.

## Required Hosted Variables

- `SL_LEGAL_API_BASE_URL`: HTTPS or HTTP API base URL for the V2 backend.
- `SL_LEGAL_AUTH_HMAC_SECRET`: 32+ character HMAC signing secret for server-side API calls.
- `SL_LEGAL_UI_SESSION_SECRET`: 32+ character UI session signing secret.
- `SL_LEGAL_UI_SESSION_COOKIE_NAME`: optional cookie name, defaulting to `sl_legal_session`.

For staging and production, `SL_LEGAL_UI_USER_ID` must not be set. The UI must use a signed session cookie rather than the local development fallback.

## Evidence Inputs

The Phase 30 report verifies:

- Phase 29 detached browser workflow log contains `exit_status=0`.
- Phase 29 browser workflow contract exists.
- Phase 29 release note exists.
- `web/package.json` exposes `phase29:e2e`.
- `scripts/run_detached_quality_gate.sh` exposes `phase29-browser-workflow`.
- `.env.example` documents the local UI environment names.

## Commands

Local readiness without secret inspection:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness phase30-ui-deployment-readiness
```

Hosted environment review from a staging/production shell:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness-env phase30-ui-deployment-readiness-env
```

Manual report command:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/build_phase30_ui_deployment_readiness.py \
  --output logs/readiness/phase30-ui-deployment-readiness.json
```

Manual hosted environment command:

```bash
PYTHONPATH=rag uv run --with pydantic python scripts/build_phase30_ui_deployment_readiness.py \
  --include-environment \
  --deployment-environment staging \
  --output logs/readiness/phase30-ui-deployment-readiness-env.json
```

## Acceptance Criteria

- The readiness manifest loads and validates.
- Local Phase 29 browser workflow evidence is present and passing.
- Environment checks do not print secret values.
- Missing hosted secrets block only when environment inspection is explicitly requested.
- Staging/production blocks if `SL_LEGAL_UI_USER_ID` is set.
- Detached backend tests and frontend quality gate pass.
- Secret scan and marker scan pass.

