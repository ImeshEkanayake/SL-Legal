# V2 Phase 9 Release: Release Artifact Bundle

## Release Goal

Phase 9 adds a release artifact packaging layer so release evidence can be checksummed, bundled, and attached outside normal Git.

## Included

- `rag/evals/phase9_release_artifacts_manifest.json`: approved artifact manifest.
- `rag/sl_legal_rag/operations.py`: artifact validation, checksum, and report helpers.
- `scripts/build_phase9_release_artifacts.py`: artifact report and optional bundle builder.
- `scripts/run_detached_quality_gate.sh`: `artifact-report` and `artifact-report-production` modes.
- `Docs/v2_phase_9_release_artifact_contract.md`: artifact contract.
- `Docs/v2_phase_9_release_artifact_runbook.md`: artifact runbook.
- `tests/test_phase9_release_artifacts.py`: artifact report and bundle tests.
- Roadmap, codebase map, and V2 version docs updated.

## Production Readiness Criteria

Phase 9 is releasable when:

- Artifact manifest covers required local release files.
- Artifact report includes SHA-256 checksums and missing-required classification.
- Local artifact report is complete.
- Production artifact report records missing production evidence until real reports exist.
- Backend and frontend detached gates pass.
- Load-plan and readiness-pack gates pass.
- Secret scan and marker scan pass.
- No V1 code, raw data, evidence logs, artifact tarballs, or database schema is committed.

## Validation Results

Local targeted validation completed on 2026-05-28:

- Focused Phase 9 unit tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic python -m pytest tests/test_phase9_release_artifacts.py -q`
  - Result: `4 passed in 0.02s`.
- Syntax checks:
  - Command: `python3 -m py_compile rag/sl_legal_rag/operations.py scripts/build_phase9_release_artifacts.py`
  - Result: passed.
- Local artifact report:
  - Command: `PYTHONPATH=rag python3 scripts/build_phase9_release_artifacts.py --output logs/release-artifacts/phase9-artifact-report-local.json --write-bundle --bundle logs/release-artifacts/phase9-release-evidence-local.tar.gz`
  - Result: `complete`, `8` present, `0` missing, `0` required missing.
- Production artifact report review:
  - Command: `PYTHONPATH=rag python3 scripts/build_phase9_release_artifacts.py --include-production --allow-missing --output logs/release-artifacts/phase9-artifact-report-production-plan.json --write-bundle --bundle logs/release-artifacts/phase9-release-evidence-production-plan.tar.gz`
  - Result: `incomplete`, `9` present, `2` missing, `2` required missing; missing reports are real signed load and full searchability audit.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag python3 -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.
- Detached backend tests:
  - Log: `logs/test-runs/phase9-tests.log`
  - Result: `255 passed in 0.81s`, exit `0`.
- Detached frontend quality:
  - Log: `logs/test-runs/phase9-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next.js build passed, `npm audit --audit-level=moderate` found `0` vulnerabilities, exit `0`.
- Detached load-plan gate:
  - Log: `logs/test-runs/phase9-load-plan.log`
  - Result: five-scenario plan rendered, exit `0`.
- Detached readiness pack:
  - Log: `logs/test-runs/phase9-readiness-pack.log`
  - Result: decision `ready`, exit `0`.
- Detached local artifact report:
  - Log: `logs/test-runs/phase9-artifact-report.log`
  - Result: `complete`, `8` present, `0` required missing, exit `0`.
- Detached production artifact report review:
  - Log: `logs/test-runs/phase9-artifact-report-production.log`
  - Result: `incomplete`, `2` required production files missing, exit `0` because missing production artifacts were allowed for review.
- Bundle content check:
  - Command: `tar -tzf logs/release-artifacts/phase9-release-evidence.tar.gz`
  - Result: bundle contains approved docs, manifests, local readiness pack, and artifact report only.

## Production Deployment Note

This release does not claim production cutover. Production evidence artifacts remain incomplete until the hosted-stack schema, health, index, load, and searchability reports exist.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No evidence artifact upload in normal Git.
- No database migration.
- No production cutover.

## Next Phase

The next phase can attach real production evidence artifacts to the GitHub release or object storage after hosted-service checks are run.
