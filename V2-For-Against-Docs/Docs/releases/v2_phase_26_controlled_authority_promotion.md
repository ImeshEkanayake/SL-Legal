# V2 Phase 26 Release: Controlled Authority Promotion

## Release Goal

Phase 26 allows only verified authority expansion child-pack items to become citable authority references in matter memory.

## Included

- `rag/sl_legal_rag/models.py`: adds `authority_pack_promotion.v1` request, item, record, and response contracts.
- `rag/sl_legal_rag/db/repositories.py`: promotes verified child-pack items under a draft row lock and updates matter memory.
- `rag/sl_legal_rag/api.py`: adds the child-pack promotion endpoint and audit event.
- `web/src/lib/workspace-types.ts`: adds frontend promotion record types.
- `web/src/components/DocumentWorkspace.tsx`: shows promoted item count and citable state.
- `web/src/components/CaseWorkspace.test.tsx`: updates the workspace fixture.
- `tests/test_agentic_research_models.py`: validates promotion boundaries.
- `tests/test_api_research_pack_endpoint.py`: verifies the promotion endpoint and audit event.
- `tests/test_db_access_layer.py`: verifies verification-to-promotion metadata persistence.
- `Docs/v2_phase_26_controlled_authority_promotion_contract.md`: promotion contract.

## Production Readiness Criteria

Phase 26 is releasable when:

- promotion requires an executed and fully verified child pack;
- promotion rejects unverified, needs-review, unknown, or duplicate pack items;
- candidate authorities receive `promoted_pack_item_ids` only after promotion;
- matter memory records the promoted child pack as sealed;
- promotion writes an audit event;
- no V1, raw data, or database migration changes are introduced.

## Validation Results

Local targeted validation completed on 2026-05-30:

- Python compile check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/models.py rag/sl_legal_rag/api.py rag/sl_legal_rag/db/repositories.py`
  - Result: passed.
- Authority promotion model/API tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_agentic_research_models.py tests/test_api_research_pack_endpoint.py::test_authority_pack_expansion_promote_endpoint_records_citable_items -q`
  - Result: `15 passed`.
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
  - Command: `scripts/run_detached_quality_gate.sh tests phase26-controlled-authority-promotion-tests`
  - Log: `logs/test-runs/phase26-controlled-authority-promotion-tests.log`
  - Result: `314 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase26-controlled-authority-promotion-frontend`
  - Log: `logs/test-runs/phase26-controlled-authority-promotion-frontend.log`
  - Result: ESLint passed, Vitest `16 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No automatic final legal advice generation.

## Next Phase

The next step should run a full 10-case scenario validation using the promoted authority path and report whether promotion improves lawyer-review readiness.
