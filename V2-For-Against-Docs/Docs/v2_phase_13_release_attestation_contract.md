# V2 Phase 13 Release Attestation Envelope Contract

## Scope

Phase 13 creates a deterministic local attestation envelope for the latest completed V2 release. The envelope binds the GitHub release, tag commit, Phase 12 provenance ledger, release documents, and provenance manifest into an in-toto-style statement with a canonical SHA-256 digest.

No V1 files, raw corpus data, release logs, release bundles, or database schema are committed.

## Attestation Target

The canonical attestation manifest is:

```text
rag/evals/phase13_release_attestation.json
```

Default target:

```text
repo: ImeshEkanayake/SL-Legal
release: v2-phase-12-release-provenance-ledger
```

## Attestation Command

Run:

```bash
PYTHONPATH=rag python3 scripts/build_phase13_release_attestation.py \
  --output logs/release-artifacts/phase13-release-attestation.json
```

Detached:

```bash
scripts/run_detached_quality_gate.sh release-attestation phase13-release-attestation
```

## Verification Rules

The attestation is `verified` only when:

- GitHub release metadata matches the expected tag;
- the release is not draft or prerelease;
- the target tag commit is resolvable and matches the remote tag commit;
- every required subject exists and has a SHA-256 checksum;
- required JSON subjects have the expected status;
- the canonical attestation statement can be hashed deterministically.

Subject states:

- `verified`: subject exists and matches its rule.
- `missing`: required subject file is absent.
- `failed`: subject exists but does not match its rule.

## Signature Boundary

Phase 13 creates a checksum-backed local attestation envelope. It does not claim key-backed cryptographic signing. The `signature.signed` field is intentionally `false` until a reviewed signing-key workflow is approved.

## Safety Boundaries

- The attestation does not upload assets.
- The attestation does not download raw corpus data.
- Generated attestation envelopes remain local evidence and are not committed to normal Git.
- A failed attestation blocks treating the prior release as fully attestable.
