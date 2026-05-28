# V2 Phase 10 Release: Release Asset Publication

## Release Goal

Phase 10 adds a controlled workflow for planning and optionally uploading approved evidence assets to GitHub releases.

## Included

- `rag/evals/phase10_release_asset_publication.json`: publication manifest.
- `rag/sl_legal_rag/operations.py`: publication manifest validation, allowed-path checks, checksums, and plan generation.
- `scripts/publish_phase10_release_assets.py`: plan-by-default GitHub release asset publisher.
- `scripts/run_detached_quality_gate.sh`: `asset-publication-plan` mode.
- `Docs/v2_phase_10_release_asset_publication_contract.md`: publication contract.
- `Docs/v2_phase_10_release_asset_publication_runbook.md`: publication runbook.
- `tests/test_phase10_release_publication.py`: publication plan tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 10 is releasable when:

- Publication manifest targets the intended GitHub release.
- Plan mode validates asset existence, allowed paths, sizes, and SHA-256 digests.
- Raw data and runtime paths are blocked.
- Detached asset-publication-plan gate passes.
- Backend and frontend detached gates pass.
- Secret scan and marker scan pass.
- No V1 code, raw data, generated logs, release asset bundles, or database schema is committed.

## Validation Results

Local targeted validation completed on 2026-05-28:

- Focused Phase 10 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase10_release_publication.py -q`
  - Result: `4 passed in 0.02s`.
- Syntax checks:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/publish_phase10_release_assets.py`
  - Result: passed.
- Publication plan render:
  - Command: `PYTHONPATH=rag python3 scripts/publish_phase10_release_assets.py --output logs/release-artifacts/phase10-publication-plan-local.json`
  - Result: `ready`, `2` approved assets, `0` blockers.
- Publication execution:
  - Command: `PYTHONPATH=rag python3 scripts/publish_phase10_release_assets.py --execute --clobber --output logs/release-artifacts/phase10-publication-result.json`
  - Result: published `phase9-release-evidence.tar.gz` and `phase9-artifact-report.json` to `v2-phase-9-release-artifacts`.
- Published asset verification:
  - Command: `gh release view v2-phase-9-release-artifacts --repo ImeshEkanayake/SL-Legal --json assets`
  - Result: both assets uploaded with SHA-256 digests.
- Bundle content check:
  - Command: `tar -tzf logs/release-artifacts/phase9-release-evidence.tar.gz`
  - Result: bundle contains approved docs, manifests, local readiness pack, and artifact report only.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.
- Detached backend tests:
  - Log: `logs/test-runs/phase10-tests.log`
  - Result: `259 passed in 0.87s`, exit `0`.
- Detached frontend quality:
  - Log: `logs/test-runs/phase10-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next.js build passed, `npm audit --audit-level=moderate` found `0` vulnerabilities, exit `0`.
- Detached load-plan gate:
  - Log: `logs/test-runs/phase10-load-plan.log`
  - Result: five-scenario plan rendered, exit `0`.
- Detached artifact report:
  - Log: `logs/test-runs/phase10-artifact-report.log`
  - Result: `complete`, `8` present, `0` required missing, exit `0`.
- Detached asset-publication plan:
  - Log: `logs/test-runs/phase10-asset-publication-plan.log`
  - Result: `ready`, `2` approved assets, `0` blockers, exit `0`.

## Publication Note

This phase ships the safe publication workflow. The default command is a plan and does not mutate GitHub. During this release, the reviewed plan was executed and the approved Phase 9 local evidence assets were attached to the Phase 9 GitHub release.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No unreviewed release asset upload.
- No database migration.
- No production cutover.

## Next Phase

The next phase can execute the reviewed publication plan or add object-storage publication for production evidence bundles.
