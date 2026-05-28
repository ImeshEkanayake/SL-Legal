# V2 Phase 12 Release: Release Provenance Ledger

## Release Goal

Phase 12 creates a machine-readable provenance ledger for the latest completed phase, tying the GitHub release, tag commit, release documents, detached validation logs, and verification reports into one auditable record.

## Included

- `rag/evals/phase12_release_provenance.json`: required provenance evidence manifest.
- `rag/sl_legal_rag/operations.py`: provenance manifest, evidence, release metadata, and tag verification helpers.
- `scripts/build_phase12_release_provenance.py`: provenance ledger builder.
- `scripts/run_detached_quality_gate.sh`: `release-provenance` mode.
- `Docs/v2_phase_12_release_provenance_contract.md`: provenance contract.
- `Docs/v2_phase_12_release_provenance_runbook.md`: provenance runbook.
- `tests/test_phase12_release_provenance.py`: provenance tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 12 is releasable when:

- The Phase 11 GitHub release is verified by tag, URL, draft status, and prerelease status.
- The Phase 11 tag commit resolves and matches the remote tag commit.
- Required Phase 11 docs, detached logs, and JSON verification reports are present and checksummed.
- Missing evidence, failed detached logs, draft releases, or tag mismatches fail the ledger.
- Backend and frontend detached gates pass.
- Secret scan and marker scan pass.
- No V1 code, raw data, generated logs, release bundles, or database schema is committed.

## Validation Results

Local targeted validation completed on 2026-05-28:

- Focused Phase 12 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase12_release_provenance.py -q`
  - Result: `5 passed`.
- Syntax checks:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase12_release_provenance.py && bash -n scripts/run_detached_quality_gate.sh`
  - Result: passed.
- Live provenance ledger:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/build_phase12_release_provenance.py --output logs/release-artifacts/phase12-release-provenance-ledger-local.json`
  - Result: `verified`, `9` verified evidence items, `0` failed, `0` missing.
  - Verified Phase 11 tag commit: `4535f3d7718725d8f7e8c116c2296ba05fceb96d`.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.

Detached gate results:

- Backend tests:
  - Log: `logs/test-runs/phase12-tests.log`
  - Result: `270 passed`, exit `0`.
- Frontend quality:
  - Log: `logs/test-runs/phase12-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next build passed, `npm audit` found `0` vulnerabilities, exit `0`.
- Load-plan gate:
  - Log: `logs/test-runs/phase12-load-plan.log`
  - Result: planned load scenarios generated, exit `0`.
- Artifact-report gate:
  - Log: `logs/test-runs/phase12-artifact-report.log`
  - Result: local artifact report `complete`, exit `0`.
- Asset-verification gate:
  - Log: `logs/test-runs/phase12-asset-verification.log`
  - Result: `verified`, `2` verified, `0` failed, exit `0`.
- Release-provenance gate:
  - Log: `logs/test-runs/phase12-release-provenance.log`
  - Result: `verified`, `9` evidence items verified, `0` failed, `0` missing, exit `0`.

## Publication Note

This phase does not upload new release assets. It produces a local provenance ledger for audit and release review.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No new release asset labels.
- No database migration.
- No production cutover.

## Next Phase

The next phase can add signed provenance attestations or extend the ledger to hosted production evidence when those production-stack reports exist.
