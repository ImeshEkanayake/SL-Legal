# V2 Phase 11 Published Asset Verification Runbook

## Prerequisites

Generate and publish approved Phase 9 assets first:

```bash
scripts/run_detached_quality_gate.sh artifact-report phase9-artifact-report
PYTHONPATH=rag python3 scripts/publish_phase10_release_assets.py --execute --clobber
```

## Verify Published Assets

Run:

```bash
scripts/run_detached_quality_gate.sh asset-verification phase11-asset-verification
```

Review:

```text
logs/release-artifacts/phase11-asset-verification.json
```

Expected:

```text
status=verified
```

The Phase 9 evidence bundle is built with deterministic tar/gzip metadata. Re-running the artifact report gate should not change the bundle SHA-256 when the source evidence files are unchanged.

## Manual Verification

Inspect GitHub release assets:

```bash
gh release view v2-phase-9-release-artifacts \
  --repo ImeshEkanayake/SL-Legal \
  --json assets
```

Check that:

- `phase9-release-evidence.tar.gz` is uploaded;
- `phase9-artifact-report.json` is uploaded;
- GitHub digests match local digests;
- GitHub sizes match local sizes.

## Failure Handling

If an asset is missing:

1. Re-run the Phase 10 publication plan.
2. Confirm the path is approved.
3. Re-run publication with `--execute`.
4. Re-run verification.

If an asset mismatches:

1. Regenerate the Phase 9 artifact report and bundle.
2. Confirm a second regeneration produces the same bundle SHA-256.
3. Review bundle contents.
4. Publish with `--clobber` only after review.
5. Re-run verification.
