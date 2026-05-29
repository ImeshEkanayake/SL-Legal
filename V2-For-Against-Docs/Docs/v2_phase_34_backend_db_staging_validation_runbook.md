# V2 Phase 34 Runbook: Real Backend and DB Staging Validation

## Local Readiness Gate

Run Phase 33 first:

```bash
scripts/run_detached_quality_gate.sh hosted-staging-validation phase33-hosted-staging-validation
```

Then run Phase 34:

```bash
scripts/run_detached_quality_gate.sh backend-db-staging-validation phase34-backend-db-staging-validation
```

A local-only run should return `awaiting_backend_db_staging_evidence`. That means the release package is ready to consume real hosted evidence, not that the DB-backed staging path has already been validated.

## Hosted Staging Evidence

Create evidence only inside ignored `logs/` paths.

Required JSON evidence:

```json
{
  "status": "healthy",
  "runtime": "hosted_staging",
  "backend": "real",
  "database_connected": true
}
```

Save as:

```text
logs/hosted-staging/phase34-api-health.json
```

```json
{
  "status": "healthy",
  "access_mode": "read_only",
  "migration_applied": false
}
```

Save as:

```text
logs/hosted-staging/phase34-db-readonly-health.json
```

```json
{
  "status": "no_unintended_writes",
  "write_count": 0,
  "migration_count": 0,
  "raw_data_uploaded": false
}
```

Save as:

```text
logs/hosted-staging/phase34-db-write-guard.json
```

```json
{
  "status": "accepted",
  "database_migrated": false,
  "raw_data_uploaded": false,
  "writes_reviewed": true
}
```

Save as:

```text
logs/hosted-staging/phase34-operator-db-acceptance.json
```

Required detached logs:

```text
logs/test-runs/phase34-platform-signed-workspace-smoke.log
logs/test-runs/phase34-platform-authority-workflow.log
logs/test-runs/phase34-platform-document-source-smoke.log
```

Each detached log must include `exit_status=0`.

## Validation

After attaching hosted evidence, rerun:

```bash
scripts/run_detached_quality_gate.sh backend-db-staging-validation phase34-backend-db-staging-validation
```

The expected hosted result is `backend_db_staging_validated`.

If the report returns `blocked`, inspect `blockers` in:

```text
logs/readiness/phase34-backend-db-staging-validation.json
```

## Safety Notes

- Do not run migrations during this phase.
- Do not upload raw `data/`.
- Do not commit `logs/` evidence.
- Do not paste secrets, signed cookies, or DB URLs into evidence files.
- Keep all write-path checks read-only or audit-based.
