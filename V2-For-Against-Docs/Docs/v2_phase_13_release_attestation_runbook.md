# V2 Phase 13 Release Attestation Envelope Runbook

## Prerequisites

Confirm the previous phase release exists:

```bash
gh release view v2-phase-12-release-provenance-ledger \
  --repo ImeshEkanayake/SL-Legal
```

Confirm the Phase 12 provenance ledger exists locally:

```text
logs/release-artifacts/phase12-release-provenance-ledger.json
```

## Build The Attestation

Run:

```bash
scripts/run_detached_quality_gate.sh release-attestation phase13-release-attestation
```

Review:

```text
logs/release-artifacts/phase13-release-attestation.json
```

Expected:

```text
status=verified
signature.signed=false
```

## Manual Review

Inspect the attestation and confirm:

- GitHub release status is `verified`;
- git tag status is `verified`;
- all required subjects are `verified`;
- the attestation statement includes the Phase 12 release tag and commit;
- the summary has `0` failed and `0` missing subject rows.

## Failure Handling

If release metadata fails:

1. Confirm the target tag is correct in `rag/evals/phase13_release_attestation.json`.
2. Confirm the release exists and is not draft/prerelease.
3. Re-run the attestation.

If tag commit verification fails:

1. Confirm the remote tag exists.
2. Confirm the local staging repo is pushed.
3. Re-run the attestation from the V2 folder or pass saved git metadata with `--git-json`.

If a subject is missing or failed:

1. Rebuild the Phase 12 provenance ledger if needed.
2. Confirm the subject path in the manifest.
3. Re-run the attestation.

## Signing Upgrade

Key-backed signing remains intentionally out of scope until the signing key, custody model, rotation process, and CI secret boundary are reviewed.
