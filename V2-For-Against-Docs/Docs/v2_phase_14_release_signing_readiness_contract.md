# V2 Phase 14 Release Signing Readiness Contract

## Scope

Phase 14 verifies that release signing is ready for review without enabling signing execution or adding private keys. It checks the latest completed release, Phase 13 attestation evidence, approved signing modes, and forbidden private-key file patterns.

No V1 files, raw corpus data, release logs, release bundles, private signing keys, or database schema are committed.

## Readiness Target

The canonical signing readiness manifest is:

```text
rag/evals/phase14_release_signing_readiness.json
```

Default target:

```text
repo: ImeshEkanayake/SL-Legal
release: v2-phase-13-release-attestation-envelope
```

## Readiness Command

Run:

```bash
PYTHONPATH=rag python3 scripts/build_phase14_signing_readiness.py \
  --output logs/release-artifacts/phase14-signing-readiness.json
```

Detached:

```bash
scripts/run_detached_quality_gate.sh signing-readiness phase14-signing-readiness
```

## Verification Rules

The report is `ready_for_signing_review` only when:

- GitHub release metadata matches the expected tag;
- the release is not draft or prerelease;
- the target tag commit is resolvable and matches the remote tag commit;
- every required evidence item exists and has a SHA-256 checksum;
- required JSON evidence has the expected status;
- every configured signing mode is approved;
- no forbidden private-key file patterns are present.

Approved signing modes:

- `sigstore_keyless`
- `kms_hsm`

## Execution Boundary

Signing execution is disabled by default. The readiness report may list required environment variables, but execution remains disabled unless a reviewed approval flag and environment plan are supplied in a future phase.

## Safety Boundaries

- The readiness gate does not sign artifacts.
- The readiness gate does not upload assets.
- The readiness gate does not download raw corpus data.
- Generated readiness reports remain local evidence and are not committed to normal Git.
- A blocked readiness report prevents moving to a signing workflow.
