# V2 Phase 13 Release: Release Attestation Envelope

## Release Goal

Phase 13 creates a deterministic local attestation envelope for the latest completed release, binding the GitHub release, tag commit, Phase 12 provenance ledger, release documents, and provenance manifest into a checksum-backed in-toto-style statement.

## Included

- `rag/evals/phase13_release_attestation.json`: required attestation subject manifest.
- `rag/sl_legal_rag/operations.py`: attestation subject validation, digesting, statement construction, and canonical checksum helpers.
- `scripts/build_phase13_release_attestation.py`: attestation envelope builder.
- `scripts/run_detached_quality_gate.sh`: `release-attestation` mode.
- `Docs/v2_phase_13_release_attestation_contract.md`: attestation contract.
- `Docs/v2_phase_13_release_attestation_runbook.md`: attestation runbook.
- `tests/test_phase13_release_attestation.py`: attestation tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 13 is releasable when:

- The Phase 12 GitHub release is verified by tag, URL, draft status, and prerelease status.
- The Phase 12 tag commit resolves and matches the remote tag commit.
- Required Phase 12 provenance ledger, release docs, and manifest subjects are present and checksummed.
- Failed provenance status, missing subjects, draft releases, or tag mismatches fail the attestation.
- Backend and frontend detached gates pass.
- Secret scan and marker scan pass.
- No V1 code, raw data, generated logs, release bundles, or database schema is committed.

## Validation Results

Local targeted validation completed on 2026-05-29:

- Focused Phase 13 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase13_release_attestation.py -q`
  - Result: `5 passed`.
- Syntax checks:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase13_release_attestation.py && bash -n scripts/run_detached_quality_gate.sh`
  - Result: passed.
- Live release attestation:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/build_phase13_release_attestation.py --output logs/release-artifacts/phase13-release-attestation-local.json`
  - Result: `verified`, `5` verified subjects, `0` failed, `0` missing.
  - Verified Phase 12 tag commit: `47708f3bb14f6f0f12549bce042e5565b76c3ba2`.
  - Attestation digest: `cf68658af361d0036b4949fefbd93093e9ee3f40e79142347242063bca6baa54`.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.

Detached gate results:

- Backend tests:
  - Log: `logs/test-runs/phase13-tests.log`
  - Result: `275 passed`, exit `0`.
- Frontend quality:
  - Log: `logs/test-runs/phase13-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next build passed, `npm audit` found `0` vulnerabilities, exit `0`.
- Load-plan gate:
  - Log: `logs/test-runs/phase13-load-plan.log`
  - Result: planned load scenarios generated, exit `0`.
- Artifact-report gate:
  - Log: `logs/test-runs/phase13-artifact-report.log`
  - Result: local artifact report `complete`, exit `0`.
- Asset-verification gate:
  - Log: `logs/test-runs/phase13-asset-verification.log`
  - Result: `verified`, `2` verified, `0` failed, exit `0`.
- Release-provenance gate:
  - Log: `logs/test-runs/phase13-release-provenance.log`
  - Result: `verified`, `9` evidence items verified, `0` failed, `0` missing, exit `0`.
- Release-attestation gate:
  - Log: `logs/test-runs/phase13-release-attestation.log`
  - Result: `verified`, `5` subjects verified, `0` failed, `0` missing, exit `0`.

## Signature Note

The Phase 13 envelope is checksum-backed and intentionally records `signature.signed=false`. Key-backed signing is reserved for a future reviewed signing workflow.

## Publication Note

This phase does not upload new release assets. It produces a local attestation envelope for audit and release review.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No new release asset labels.
- No database migration.
- No production cutover.
- No key-backed signing workflow.

## Next Phase

The next phase can add key-backed signing and verification once signing key custody, rotation, CI secret boundaries, and recovery procedures are reviewed.
