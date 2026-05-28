# V2 Phase 14 Release Signing Readiness Runbook

## Prerequisites

Confirm the previous phase release exists:

```bash
gh release view v2-phase-13-release-attestation-envelope \
  --repo ImeshEkanayake/SL-Legal
```

Confirm the Phase 13 attestation exists locally:

```text
logs/release-artifacts/phase13-release-attestation.json
```

## Build The Readiness Report

Run:

```bash
scripts/run_detached_quality_gate.sh signing-readiness phase14-signing-readiness
```

Review:

```text
logs/release-artifacts/phase14-signing-readiness.json
```

Expected:

```text
status=ready_for_signing_review
environment_requirements.execution_enabled=false
```

## Manual Review

Inspect the report and confirm:

- GitHub release status is `verified`;
- git tag status is `verified`;
- all required evidence rows are `verified`;
- approved signing modes are limited to `sigstore_keyless` and `kms_hsm`;
- forbidden private-key file matches are `0`;
- signing execution remains disabled.

## Failure Handling

If release metadata fails:

1. Confirm the target tag is correct in `rag/evals/phase14_release_signing_readiness.json`.
2. Confirm the release exists and is not draft/prerelease.
3. Re-run the readiness report.

If evidence is missing or failed:

1. Rebuild the Phase 13 attestation if needed.
2. Confirm the evidence path in the manifest.
3. Re-run the readiness report.

If forbidden key files are detected:

1. Stop the signing workflow.
2. Remove private key material from the workspace.
3. Rotate any exposed key through the key owner.
4. Re-run secret scan and signing readiness.

## Signing Upgrade

Actual signing remains out of scope until signing identity, issuer, Rekor/log configuration, CI permissions, key custody, rotation, and break-glass recovery procedures are reviewed.
