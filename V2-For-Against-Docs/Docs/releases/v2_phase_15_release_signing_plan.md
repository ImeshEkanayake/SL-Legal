# V2 Phase 15 Release: Release Signing Execution Plan

## Release Goal

Phase 15 adds a non-mutating signing execution plan for the latest completed release. It verifies the Phase 14 release, tag commit, signing readiness report, signing artifacts, planned signing commands, expected signature outputs, and verification commands while keeping execution disabled.

## Included

- `rag/evals/phase15_release_signing_plan.json`: signing plan manifest.
- `rag/sl_legal_rag/operations.py`: signing plan artifact validation, release/tag checks, readiness report checks, and signing command templates.
- `scripts/build_phase15_signing_plan.py`: signing plan builder.
- `scripts/run_detached_quality_gate.sh`: `signing-plan` mode.
- `Docs/v2_phase_15_release_signing_plan_contract.md`: signing plan contract.
- `Docs/v2_phase_15_release_signing_plan_runbook.md`: signing plan runbook.
- `tests/test_phase15_signing_plan.py`: signing plan tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 15 is releasable when:

- The Phase 14 GitHub release is verified by tag, URL, draft status, and prerelease status.
- The Phase 14 tag commit resolves and matches the remote tag commit.
- The Phase 14 signing readiness report exists and has status `ready_for_signing_review`.
- Required signing artifacts are present and checksummed.
- Missing artifacts, unready readiness reports, draft releases, or tag mismatches block planning.
- Signing commands are planned but not executed.
- Backend and frontend detached gates pass.
- Secret scan and marker scan pass.
- No V1 code, raw data, generated logs, release bundles, private signing keys, signature output files, or database schema is committed.

## Validation Results

Local targeted validation completed on 2026-05-29:

- Focused Phase 15 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase15_signing_plan.py -q`
  - Result: `5 passed`.
- Syntax checks:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase15_signing_plan.py && bash -n scripts/run_detached_quality_gate.sh`
  - Result: passed.
- Live signing plan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/build_phase15_signing_plan.py --output logs/release-artifacts/phase15-signing-plan-local.json`
  - Result: `planned`, `2` ready artifacts, `2` planned commands, `0` blockers.
  - Verified Phase 14 tag commit: `8916bb877a3d969c651b55e134f43872887e7f71`.
  - Signing execution: not approved.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.

Detached gate results:

- Backend tests:
  - Log: `logs/test-runs/phase15-tests.log`
  - Result: `285 passed`, exit `0`.
- Frontend quality:
  - Log: `logs/test-runs/phase15-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next build passed, `npm audit` found `0` vulnerabilities, exit `0`.
- Load-plan gate:
  - Log: `logs/test-runs/phase15-load-plan.log`
  - Result: planned load scenarios generated, exit `0`.
- Artifact-report gate:
  - Log: `logs/test-runs/phase15-artifact-report.log`
  - Result: local artifact report `complete`, exit `0`.
- Asset-verification gate:
  - Log: `logs/test-runs/phase15-asset-verification.log`
  - Result: `verified`, `2` verified, `0` failed, exit `0`.
- Signing-readiness gate:
  - Log: `logs/test-runs/phase15-signing-readiness.log`
  - Result: `ready_for_signing_review`, `5` evidence items verified, `0` forbidden private-key file matches, exit `0`.
- Signing-plan gate:
  - Log: `logs/test-runs/phase15-signing-plan.log`
  - Result: `planned`, `2` ready artifacts, `2` planned commands, `0` blockers, exit `0`.

## Signing Note

Phase 15 does not sign artifacts. It plans exact commands and expected outputs only.

## Publication Note

This phase does not upload new release assets. It produces a local signing plan for audit and release review.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No new release asset labels.
- No database migration.
- No private signing keys.
- No key-backed or keyless signing execution.
- No signature output files.

## Next Phase

The next phase can add a reviewed signing execution workflow after signing identity, issuer, transparency log, CI permission, key custody, rotation, and recovery procedures are approved.
