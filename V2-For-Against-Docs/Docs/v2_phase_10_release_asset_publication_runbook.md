# V2 Phase 10 Release Asset Publication Runbook

## Generate Assets

Build the local evidence bundle first:

```bash
scripts/run_detached_quality_gate.sh artifact-report phase9-artifact-report
```

Confirm the artifact report is complete:

```text
logs/release-artifacts/phase9-artifact-report.json
```

## Plan Publication

Run:

```bash
scripts/run_detached_quality_gate.sh asset-publication-plan phase10-asset-publication-plan
```

Review:

```text
logs/release-artifacts/phase10-publication-plan.json
```

The plan must show:

- `status: ready`
- no blockers
- target release tag is correct
- assets are under `logs/release-artifacts`
- SHA-256 digests are present

## Execute Publication

Only after review:

```bash
PYTHONPATH=rag python3 scripts/publish_phase10_release_assets.py \
  --execute \
  --clobber \
  --output logs/release-artifacts/phase10-publication-result.json
```

## Verification

After execution:

```bash
gh release view v2-phase-9-release-artifacts \
  --repo ImeshEkanayake/SL-Legal \
  --json assets
```

Expected assets:

- `phase9-release-evidence.tar.gz`
- `phase9-artifact-report.json`

## Failure Handling

If the plan is blocked:

1. Check missing asset paths.
2. Regenerate Phase 9 artifacts if needed.
3. Confirm paths do not point to raw data or runtime folders.
4. Re-run the plan.

If GitHub upload fails:

1. Check `gh auth status`.
2. Confirm release tag exists.
3. Re-run with `--clobber` only when replacing the same reviewed asset.
