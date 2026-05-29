# V2 Phase 23 Release: Authority Expansion Idempotency

## Release Goal

Phase 23 fixes the authority expansion execution race found during full code review.

## Included

- `rag/sl_legal_rag/db/repositories.py`: adds locked draft metadata reads and uses them when recording authority expansion execution.
- `rag/sl_legal_rag/api.py`: performs a locked duplicate re-check before recording execution.
- `tests/test_api_research_pack_endpoint.py`: covers the locked duplicate re-check and `409 Conflict` behavior.
- `Docs/v2_phase_23_authority_expansion_idempotency_contract.md`: locking and idempotency contract.
- `Docs/v2_codebase_map.md`: Phase 23 code map.
- `Docs/v2_production_product_roadmap.md`: Phase 23 roadmap entry.

## Production Readiness Criteria

Phase 23 is releasable when:

- duplicate checks and metadata append run under a draft row lock;
- API re-checks duplicate execution with `lock_draft = true`;
- duplicate execution returns `409 Conflict`;
- successful execution behavior remains unchanged;
- candidate authorities remain non-citable and unpromoted.

## Validation Results

Local targeted validation completed on 2026-05-30:

- Authority expansion conflict and repository tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_api_research_pack_endpoint.py::test_authority_pack_expansion_execute_endpoint_records_child_pack tests/test_api_research_pack_endpoint.py::test_authority_pack_expansion_execute_endpoint_rechecks_duplicate_under_lock tests/test_db_access_layer.py::test_db_access_layer_vertical_workflow_rolls_back -q`
  - Result: `3 passed`.
- Python compile check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/api.py rag/sl_legal_rag/db/repositories.py`
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
  - Command: `scripts/run_detached_quality_gate.sh tests phase23-authority-expansion-idempotency-tests`
  - Log: `logs/test-runs/phase23-authority-expansion-idempotency-tests.log`
  - Result: `308 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase23-authority-expansion-idempotency-frontend`
  - Log: `logs/test-runs/phase23-authority-expansion-idempotency-frontend.log`
  - Result: ESLint passed, Vitest `16 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No pre-retrieval reservation table.
- No authority promotion.
- No final legal advice generation.

## Next Phase

The next step should move from post-retrieval conflict handling to a true execution reservation or DB-backed execution table before source anchoring and authority promotion.
