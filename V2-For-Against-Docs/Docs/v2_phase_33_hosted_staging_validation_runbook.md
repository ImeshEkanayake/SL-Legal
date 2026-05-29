# V2 Phase 33 Runbook: Hosted Staging Execution Validation

## Local Validation

Generate Phase 32 evidence first:

```bash
scripts/run_detached_quality_gate.sh hosted-staging-execution-pack phase32-hosted-staging-execution-pack
```

Then run Phase 33:

```bash
scripts/run_detached_quality_gate.sh hosted-staging-validation phase33-hosted-staging-validation
```

Expected local result:

- `exit_status=0`
- report status `awaiting_hosted_execution`

This is the correct local result. It means the local code and prerequisite artifacts are ready, but the hosted staging evidence has not been attached.

## Hosted Staging Validation

Inside the hosted staging execution environment, run:

```bash
scripts/run_detached_quality_gate.sh ui-deployment-readiness-env phase33-hosted-env-readiness
scripts/run_detached_quality_gate.sh staging-cutover-dry-run phase33-hosted-cutover-dry-run
scripts/run_detached_quality_gate.sh hosted-staging-execution-pack phase33-hosted-execution-pack
scripts/run_detached_quality_gate.sh phase29-browser-workflow phase33-platform-browser-smoke
scripts/run_detached_quality_gate.sh tests phase33-platform-tests
scripts/run_detached_quality_gate.sh frontend phase33-platform-frontend
```

Then write local hosted-staging approval records:

```json
{"status":"approved","reviewed_by":"operator","notes":"Hosted secrets configured only in deployment platform."}
```

Save that as:

```text
logs/hosted-staging/phase33-operator-secret-review.json
```

For lawyer-owner acceptance:

```json
{"status":"accepted","reviewed_by":"lawyer-owner","notes":"Hosted staging UI accepted for private review workflow."}
```

Save that as:

```text
logs/hosted-staging/phase33-lawyer-owner-acceptance.json
```

Do not commit these files. They are hosted execution evidence and remain under ignored `logs/`.

## Final Hosted Gate

Run:

```bash
scripts/run_detached_quality_gate.sh hosted-staging-validation phase33-hosted-staging-validation
```

Expected hosted result:

- `exit_status=0`
- report status `hosted_staging_validated`
- zero blockers
- no secrets or session tokens in the report

## If Blocked

- If Phase 30 is not `ready_for_deployment_review`, fix hosted env vars.
- If Phase 31 is not `ready_for_staging_cutover`, rerun cutover dry-run after hosted env validation.
- If Phase 32 is not `ready_for_hosted_staging_execution`, rerun the execution pack after Phase 31 passes.
- If smoke logs fail, keep the failed logs for diagnosis and restore previous staging deployment.
- If an approval is rejected, do not proceed to production planning.
