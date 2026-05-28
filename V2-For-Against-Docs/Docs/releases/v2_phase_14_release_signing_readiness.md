# V2 Phase 14 Release: Release Signing Readiness

## Release Goal

Phase 14 adds a signing readiness gate for the latest completed release. It verifies the Phase 13 release, tag commit, attestation evidence, approved signing modes, and absence of forbidden private-key files while keeping signing execution disabled by default.

## Included

- `rag/evals/phase14_release_signing_readiness.json`: signing readiness manifest.
- `rag/sl_legal_rag/operations.py`: signing readiness evidence validation, release/tag checks, approved signing mode validation, and forbidden private-key scans.
- `scripts/build_phase14_signing_readiness.py`: signing readiness report builder.
- `scripts/run_detached_quality_gate.sh`: `signing-readiness` mode.
- `Docs/v2_phase_14_release_signing_readiness_contract.md`: signing readiness contract.
- `Docs/v2_phase_14_release_signing_readiness_runbook.md`: signing readiness runbook.
- `tests/test_phase14_signing_readiness.py`: signing readiness tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 14 is releasable when:

- The Phase 13 GitHub release is verified by tag, URL, draft status, and prerelease status.
- The Phase 13 tag commit resolves and matches the remote tag commit.
- Required Phase 13 attestation envelope, release docs, and manifest evidence are present and checksummed.
- Unsupported signing modes, forbidden private-key files, failed evidence, draft releases, or tag mismatches block readiness.
- Signing execution remains disabled by default.
- Backend and frontend detached gates pass.
- Secret scan and marker scan pass.
- No V1 code, raw data, generated logs, release bundles, private signing keys, or database schema is committed.

## Validation Results

Local targeted validation completed on 2026-05-29:

- Focused Phase 14 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase14_signing_readiness.py -q`
  - Result: `5 passed`.
- Syntax checks:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase14_signing_readiness.py && bash -n scripts/run_detached_quality_gate.sh`
  - Result: passed.
- Live signing readiness report:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/build_phase14_signing_readiness.py --output logs/release-artifacts/phase14-signing-readiness-local.json`
  - Result: `ready_for_signing_review`, `5` verified evidence items, `0` forbidden private-key file matches.
  - Verified Phase 13 tag commit: `6f328ddd0f31ae6ad0bdb35e4f6e13863f6eacba`.
  - Signing execution: disabled.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.

Detached gate results:

- Backend tests:
  - Log: `logs/test-runs/phase14-tests.log`
  - Result: `280 passed`, exit `0`.
- Frontend quality:
  - Log: `logs/test-runs/phase14-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next build passed, `npm audit` found `0` vulnerabilities, exit `0`.
- Load-plan gate:
  - Log: `logs/test-runs/phase14-load-plan.log`
  - Result: planned load scenarios generated, exit `0`.
- Artifact-report gate:
  - Log: `logs/test-runs/phase14-artifact-report.log`
  - Result: local artifact report `complete`, exit `0`.
- Asset-verification gate:
  - Log: `logs/test-runs/phase14-asset-verification.log`
  - Result: `verified`, `2` verified, `0` failed, exit `0`.
- Release-attestation gate:
  - Log: `logs/test-runs/phase14-release-attestation.log`
  - Result: `verified`, `5` subjects verified, `0` failed, `0` missing, exit `0`.
- Signing-readiness gate:
  - Log: `logs/test-runs/phase14-signing-readiness.log`
  - Result: `ready_for_signing_review`, `5` evidence items verified, `0` forbidden private-key file matches, exit `0`.

## Signing Note

Phase 14 does not sign artifacts. It establishes the readiness controls needed before a future signing workflow can be reviewed.

## Publication Note

This phase does not upload new release assets. It produces a local signing readiness report for audit and release review.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No new release asset labels.
- No database migration.
- No private signing keys.
- No key-backed or keyless signing execution.

## Next Phase

The next phase can implement a reviewed signing execution workflow after signing identity, issuer, transparency log, CI permission, key custody, rotation, and recovery procedures are approved.
