# V2 Phase 25 Release: Child Pack Source Anchoring and Authority Verification

## Release Goal

Phase 25 verifies executed authority expansion child packs against source anchors before any authority promotion work begins.

## Included

- `rag/sl_legal_rag/models.py`: adds `authority_pack_verification.v1` and per-item verification records.
- `rag/sl_legal_rag/db/repositories.py`: verifies executed child packs under a draft row lock and persists verification metadata.
- `rag/sl_legal_rag/api.py`: adds the child-pack verification endpoint and audit event.
- `web/src/lib/workspace-types.ts`: adds frontend verification record types.
- `web/src/components/DocumentWorkspace.tsx`: shows child-pack verification status, anchored count, review count, and non-citable state.
- `web/src/components/CaseWorkspace.test.tsx`: updates the workspace fixture.
- `tests/test_agentic_research_models.py`: validates verification boundaries.
- `tests/test_api_research_pack_endpoint.py`: verifies the API response and audit event.
- `tests/test_db_access_layer.py`: verifies execution-to-verification metadata persistence.
- `Docs/v2_phase_25_child_pack_authority_verification_contract.md`: verification contract.

## Production Readiness Criteria

Phase 25 is releasable when:

- verification only accepts executed child packs;
- child pack hashes match execution records;
- verified items require source anchors and citations;
- weak, incomplete, or unanchored items are marked for lawyer review;
- verification records remain non-citable;
- candidate authorities remain unpromoted.

## Validation Results

Local targeted validation completed on 2026-05-30:

- Python compile check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/models.py rag/sl_legal_rag/api.py rag/sl_legal_rag/db/repositories.py`
  - Result: passed.
- Authority verification model/API tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_agentic_research_models.py tests/test_api_research_pack_endpoint.py::test_authority_pack_expansion_verify_endpoint_records_source_anchoring -q`
  - Result: `14 passed`.
- Rollback-only database workflow:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_db_access_layer.py::test_db_access_layer_vertical_workflow_rolls_back -q`
  - Result: `1 passed`.
- Frontend workspace component test:
  - Command: `npm --prefix web test -- CaseWorkspace.test.tsx --run`
  - Result: `13 passed`.
- Frontend lint:
  - Command: `npm --prefix web run lint`
  - Result: passed.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers(); print("marker scan passed")'`
  - Result: passed.

Detached validation completed on 2026-05-30:

- Backend test suite:
  - Command: `scripts/run_detached_quality_gate.sh tests phase25-child-pack-verification-tests`
  - Log: `logs/test-runs/phase25-child-pack-verification-tests.log`
  - Result: `312 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase25-child-pack-verification-frontend`
  - Log: `logs/test-runs/phase25-child-pack-verification-frontend.log`
  - Result: ESLint passed, Vitest `16 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No authority promotion.
- No final legal advice generation.

## Next Phase

The next step should define controlled authority promotion from verified child-pack items into sealed, citable research-pack authority records.
