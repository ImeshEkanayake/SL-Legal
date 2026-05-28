# V2 Phase 11 Published Asset Verification Contract

## Scope

Phase 11 verifies that published GitHub release assets match the approved local release artifact files by SHA-256 digest and byte size.

No V1 files, raw corpus data, release logs, release bundles, or database schema are committed.

## Verification Target

The verifier uses the Phase 10 publication manifest:

```text
rag/evals/phase10_release_asset_publication.json
```

Default target:

```text
repo: ImeshEkanayake/SL-Legal
release: v2-phase-9-release-artifacts
```

## Verification Command

Run:

```bash
PYTHONPATH=rag python3 scripts/verify_phase11_release_assets.py \
  --output logs/release-artifacts/phase11-asset-verification.json
```

Detached:

```bash
scripts/run_detached_quality_gate.sh asset-verification phase11-asset-verification
```

## Verification Rules

Each asset must satisfy:

- remote asset exists by expected label/name;
- local approved file exists;
- local release bundles are rebuilt with deterministic archive metadata;
- remote SHA-256 digest equals local SHA-256 digest;
- remote byte size equals local byte size;
- publication path remains an approved `logs/release-artifacts/` path.

Statuses:

- `verified`: remote and local asset match.
- `missing_remote`: GitHub release asset is absent.
- `mismatch`: digest or size differs.

## Safety Boundaries

- Verification does not upload assets.
- Controlled re-publication, when needed after a mismatch investigation, remains a separate explicit Phase 10 publication action.
- Verification does not download raw corpus data.
- Verification reports are local evidence and are not committed to normal Git.
- A mismatch blocks trusting the published release asset.
