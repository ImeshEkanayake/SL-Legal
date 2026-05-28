# V2 Phase 12 Release Provenance Ledger Runbook

## Prerequisites

Confirm the previous phase release exists:

```bash
gh release view v2-phase-11-published-asset-verification \
  --repo ImeshEkanayake/SL-Legal
```

Confirm Phase 11 verification evidence exists locally:

```text
logs/release-artifacts/phase11-asset-verification.json
logs/test-runs/phase11-tests-rerun.log
logs/test-runs/phase11-frontend-rerun.log
logs/test-runs/phase11-load-plan-rerun.log
logs/test-runs/phase11-artifact-report-rerun.log
logs/test-runs/phase11-asset-verification-rerun.log
```

## Build The Ledger

Run:

```bash
scripts/run_detached_quality_gate.sh release-provenance phase12-release-provenance
```

Review:

```text
logs/release-artifacts/phase12-release-provenance-ledger.json
```

Expected:

```text
status=verified
```

## Manual Review

Inspect the ledger and confirm:

- GitHub release status is `verified`;
- git tag status is `verified`;
- all required evidence rows are `verified`;
- the summary has `0` failed and `0` missing evidence rows.

## Failure Handling

If release metadata fails:

1. Confirm the target tag is correct in `rag/evals/phase12_release_provenance.json`.
2. Confirm the release exists and is not draft/prerelease.
3. Re-run the ledger.

If tag commit verification fails:

1. Confirm the remote tag exists.
2. Confirm the local staging repo is pushed.
3. Re-run the ledger from the V2 folder or pass saved git metadata with `--git-json`.

If evidence is missing or failed:

1. Re-run the relevant detached gate.
2. Confirm the evidence path in the manifest.
3. Re-run the ledger.
