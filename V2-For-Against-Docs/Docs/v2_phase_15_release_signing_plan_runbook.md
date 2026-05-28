# V2 Phase 15 Release Signing Execution Plan Runbook

## Prerequisites

Confirm the previous phase release exists:

```bash
gh release view v2-phase-14-release-signing-readiness \
  --repo ImeshEkanayake/SL-Legal
```

Confirm the Phase 14 signing readiness report exists locally:

```text
logs/release-artifacts/phase14-signing-readiness.json
```

## Build The Plan

Run:

```bash
scripts/run_detached_quality_gate.sh signing-plan phase15-signing-plan
```

Review:

```text
logs/release-artifacts/phase15-signing-plan.json
```

Expected:

```text
status=planned
signing_execution_approved=false
```

## Manual Review

Inspect the plan and confirm:

- GitHub release status is `verified`;
- git tag status is `verified`;
- readiness report status is `ready_for_signing_review`;
- every artifact is `ready`;
- planned commands match the approved signing mode;
- expected signature outputs are under `logs/release-artifacts/signatures`;
- no signing command has been executed.

## Failure Handling

If release metadata fails:

1. Confirm the target tag is correct in `rag/evals/phase15_release_signing_plan.json`.
2. Confirm the release exists and is not draft/prerelease.
3. Re-run the signing plan.

If readiness is not ready:

1. Re-run the Phase 14 signing readiness gate.
2. Confirm the readiness report path in the manifest.
3. Re-run the signing plan.

If an artifact is missing:

1. Rebuild the missing local release artifact.
2. Confirm the artifact path in the manifest.
3. Re-run the signing plan.

## Execution Upgrade

Actual signing remains out of scope until a future phase approves signing execution, identity, issuer, transparency log, CI permission boundary, key custody, rotation, and recovery procedures.
