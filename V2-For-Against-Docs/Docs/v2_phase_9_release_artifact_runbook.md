# V2 Phase 9 Release Artifact Runbook

## Local Artifact Report

Run after local Phase 9 release gates pass:

```bash
scripts/run_detached_quality_gate.sh artifact-report phase9-artifact-report
```

Expected result:

```text
status=complete
```

Generated files:

```text
logs/release-artifacts/phase9-artifact-report.json
logs/release-artifacts/phase9-release-evidence.tar.gz
```

These files are release artifacts. They are not committed to normal Git.

## Production Artifact Report

Run after production-stack reports are collected:

```bash
scripts/run_detached_quality_gate.sh artifact-report-production phase9-artifact-report-production
```

Expected before production evidence exists:

```text
status=incomplete
```

Expected before production cutover:

```text
status=complete
```

## Attachment Workflow

1. Confirm `logs/release-artifacts/phase9-artifact-report.json` is complete.
2. Confirm bundle contents do not contain raw corpus data, `.env`, logs outside the approved evidence list, `node_modules`, or `.next`.
3. Attach the bundle to the GitHub release only when it is useful for review.
4. Store production evidence bundles in release artifacts or object storage, not normal Git.

## Review Workflow

Review:

- `summary.required_missing`
- every artifact `sha256`
- every production artifact marked `missing`
- bundle file list

If required local artifacts are missing, fix the manifest path or generate the missing document before release.

If production artifacts are missing, production cutover remains blocked, but the local release package can still be published when its local report is complete.
