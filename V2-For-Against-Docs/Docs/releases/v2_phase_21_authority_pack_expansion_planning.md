# V2 Phase 21 Release: Authority Pack Expansion Planning

## Release Goal

Phase 21 turns approved authority-candidate review tasks into explicit pack-expansion plans while keeping candidate authorities non-citable.

## Included

- `rag/sl_legal_rag/models.py`: adds `AuthorityPackExpansionPlan`.
- `rag/sl_legal_rag/agentic_research.py`: builds official-source pack-expansion requests from non-citable authority candidates.
- `rag/sl_legal_rag/db/repositories.py`: stores expansion plans in existing draft metadata when authority-candidate review is approved.
- `web/src/lib/workspace-types.ts`: adds frontend workspace types for expansion plans.
- `web/src/components/DocumentWorkspace.tsx`: displays planned authority expansion queries in the reasoning workspace.
- `tests/test_agentic_research_models.py`: model boundary coverage.
- `tests/test_agentic_research_service.py`: expansion-plan builder coverage.
- `tests/test_db_access_layer.py`: integration coverage for persistence and audit metadata.
- `web/src/components/CaseWorkspace.test.tsx`: UI visibility coverage.
- `Docs/v2_phase_21_authority_pack_expansion_contract.md`: contract and phase boundary.

## Production Readiness Criteria

Phase 21 is releasable when:

- approved authority-candidate reviews create one draft-scoped expansion plan;
- all expansion requests require official-source retrieval;
- candidate authorities remain non-citable and unpromoted;
- draft metadata exposes the plan for draft detail and workspace views;
- audit metadata includes the generated plan;
- existing review queue behavior remains green.

## Validation Results

Local targeted validation completed on 2026-05-29:

- Agentic model, service, and repository tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_agentic_research_models.py tests/test_agentic_research_service.py tests/test_db_access_layer.py::test_db_access_layer_vertical_workflow_rolls_back -q`
  - Result: `13 passed`.
- Frontend workspace component test:
  - Command: `npm --prefix web test -- CaseWorkspace.test.tsx --run`
  - Result: `13 passed`.
- Python compile check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/models.py rag/sl_legal_rag/agentic_research.py rag/sl_legal_rag/db/repositories.py`
  - Result: passed.
- Frontend lint:
  - Command: `npm --prefix web run lint`
  - Result: passed.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers(); print("marker scan passed")'`
  - Result: passed.

Detached validation completed on 2026-05-29:

- Backend test suite:
  - Command: `scripts/run_detached_quality_gate.sh tests phase21-authority-expansion-tests`
  - Log: `logs/test-runs/phase21-authority-expansion-tests.log`
  - Result: `305 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase21-authority-expansion-frontend`
  - Log: `logs/test-runs/phase21-authority-expansion-frontend.log`
  - Result: ESLint passed, Vitest `16 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No retrieval execution.
- No authority sealing.
- No candidate promotion.
- No final legal advice generation.

## Next Phase

The next step should execute the planned pack-expansion request against the existing research-pack expansion endpoint, then anchor and verify returned sources before any candidate authority can be promoted.
