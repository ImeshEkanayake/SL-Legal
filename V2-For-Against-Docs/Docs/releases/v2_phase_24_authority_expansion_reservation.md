# V2 Phase 24 Release: Authority Expansion Reservation

## Release Goal

Phase 24 prevents duplicate authority expansion retrieval by reserving a planned request before child pack creation begins.

## Included

- `rag/sl_legal_rag/models.py`: adds `authority_pack_expansion_reservation.v1` records.
- `rag/sl_legal_rag/db/repositories.py`: reserves request execution under a draft row lock, completes reservations after execution, and marks reservations failed after retrieval errors.
- `rag/sl_legal_rag/api.py`: reserves before calling the research-pack expansion flow.
- `web/src/lib/workspace-types.ts`: adds frontend reservation record types.
- `web/src/components/CaseWorkspace.test.tsx`: updates the workspace fixture.
- `tests/test_agentic_research_models.py`: validates reservation uniqueness.
- `tests/test_api_research_pack_endpoint.py`: verifies duplicate reservations stop before retrieval.
- `tests/test_db_access_layer.py`: verifies reservation-to-completion metadata flow.
- `Docs/v2_phase_24_authority_expansion_reservation_contract.md`: reservation contract.

## Production Readiness Criteria

Phase 24 is releasable when:

- request reservation happens before retrieval;
- duplicate reservations return `409 Conflict` without creating or saving a child pack;
- successful execution marks reservation records `completed`;
- failed retrieval marks reservations `failed`;
- retries remain possible after failed reservations;
- candidate authorities remain non-citable and unpromoted.

## Validation Results

Local targeted validation completed on 2026-05-30:

- Authority expansion reservation tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_agentic_research_models.py tests/test_api_research_pack_endpoint.py::test_authority_pack_expansion_execute_endpoint_records_child_pack tests/test_api_research_pack_endpoint.py::test_authority_pack_expansion_execute_endpoint_reserves_before_retrieval tests/test_db_access_layer.py::test_db_access_layer_vertical_workflow_rolls_back -q`
  - Result: `14 passed`.
- Python compile check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/models.py rag/sl_legal_rag/api.py rag/sl_legal_rag/db/repositories.py`
  - Result: passed.
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
  - Command: `scripts/run_detached_quality_gate.sh tests phase24-authority-expansion-reservation-tests`
  - Log: `logs/test-runs/phase24-authority-expansion-reservation-tests.log`
  - Result: `309 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase24-authority-expansion-reservation-frontend`
  - Log: `logs/test-runs/phase24-authority-expansion-reservation-frontend.log`
  - Result: ESLint passed, Vitest `16 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No source anchoring.
- No authority promotion.
- No final legal advice generation.

## Next Phase

The next step should inspect executed child packs, anchor returned source passages, and verify authority metadata before any candidate promotion is allowed.
