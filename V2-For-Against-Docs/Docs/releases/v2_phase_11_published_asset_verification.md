# V2 Phase 11 Release: Published Asset Verification

## Release Goal

Phase 11 verifies that the evidence assets attached to GitHub releases match the approved local release artifact files by SHA-256 digest and byte size.

## Included

- `rag/sl_legal_rag/operations.py`: remote asset digest normalization and verification report helpers.
- `scripts/build_phase9_release_artifacts.py`: deterministic tar/gzip evidence bundle generation.
- `scripts/verify_phase11_release_assets.py`: GitHub release asset verifier.
- `scripts/run_detached_quality_gate.sh`: `asset-verification` mode.
- `Docs/v2_phase_11_published_asset_verification_contract.md`: verification contract.
- `Docs/v2_phase_11_published_asset_verification_runbook.md`: verification runbook.
- `tests/test_phase11_release_asset_verification.py`: verification tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 11 is releasable when:

- Published Phase 9 assets verify against local SHA-256 digests.
- Missing or mismatched remote assets fail verification.
- Rebuilt release bundles keep stable SHA-256 digests when source evidence is unchanged.
- Detached asset-verification gate passes.
- Backend and frontend detached gates pass.
- Secret scan and marker scan pass.
- No V1 code, raw data, generated logs, release bundles, or database schema is committed.

## Validation Results

Local targeted validation completed on 2026-05-28:

- Focused Phase 11 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase11_release_asset_verification.py -q`
  - Result: `5 passed`.
- Focused Phase 9/11 regression tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase9_release_artifacts.py tests/test_phase11_release_asset_verification.py -q`
  - Result: `10 passed`.
- Syntax checks:
  - Command: `python3 -m py_compile scripts/build_phase9_release_artifacts.py scripts/verify_phase11_release_assets.py rag/sl_legal_rag/operations.py`
  - Result: passed.
- Live asset verification:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/verify_phase11_release_assets.py --output logs/release-artifacts/phase11-asset-verification.json`
  - Result: `verified`, `2` verified, `0` failed.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.

Detached gate results:

- Backend tests:
  - Log: `logs/test-runs/phase11-tests-rerun.log`
  - Result: `265 passed`, exit `0`.
- Frontend quality:
  - Log: `logs/test-runs/phase11-frontend-rerun.log`
  - Result: lint passed, `16` Vitest tests passed, Next build passed, `npm audit` found `0` vulnerabilities, exit `0`.
- Load-plan gate:
  - Log: `logs/test-runs/phase11-load-plan-rerun.log`
  - Result: planned load scenarios generated, exit `0`.
- Artifact-report gate:
  - Log: `logs/test-runs/phase11-artifact-report-rerun.log`
  - Result: local artifact report `complete`, exit `0`.
- Asset-verification gate:
  - Log: `logs/test-runs/phase11-asset-verification-rerun.log`
  - Result: `verified`, `2` verified, `0` failed, exit `0`.

Published asset evidence after deterministic rebuild:

- `phase9-release-evidence.tar.gz`: size `5327`, SHA-256 `accf1482d7c5e9106fba7b5227e303d0acb2e1b16c684d3deb186a7bd7c0fa50`.
- `phase9-artifact-report.json`: size `3692`, SHA-256 `9f057e41054c76392975cbdc4c57a1b01d884f3bb81d048fa817fdde489e1db7`.

Phase 11 initially caught a valid drift condition: a rebuilt gzip/tar bundle had the same source evidence but a different archive digest. The bundle writer now normalizes gzip and tar metadata so repeated builds are stable. The existing Phase 9 release asset labels were republished with `--clobber` after the deterministic rebuild, then independently verified.

## Publication Note

This phase does not add new release asset labels. It verifies the assets attached to `v2-phase-9-release-artifacts` and records the controlled re-publication of the existing labels after the deterministic bundle fix.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No new release asset labels.
- No database migration.
- No production cutover.

## Next Phase

The next phase can extend verification to object-storage production evidence bundles when hosted evidence exists.
