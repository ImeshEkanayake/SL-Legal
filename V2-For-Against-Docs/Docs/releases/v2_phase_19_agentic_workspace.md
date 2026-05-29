# V2 Phase 19 Release: Agentic Workspace Visibility

## Release Goal

Phase 19 makes the Phase 18 agentic metadata visible in the lawyer workspace. The Reasoning tab now shows the agentic tool route, clarification needs, authority candidates, matter memory, and sealed-pack boundaries beside the reasoning pack.

## Included

- `rag/sl_legal_rag/models.py`: workspace draft summaries expose `agenticResearchPlan` and `matterMemory`.
- `rag/sl_legal_rag/db/repositories.py`: workspace snapshots read agentic metadata from existing draft metadata.
- `web/src/lib/workspace-types.ts`: TypeScript contracts for tool traces, authority candidates, clarification needs, agentic plans, and matter memory.
- `web/src/components/DocumentWorkspace.tsx`: agentic workflow panel in the Reasoning tab.
- `web/src/components/CaseWorkspace.test.tsx`: rendering coverage for tool route, clarification blockers, authority candidates, and matter memory.
- `tests/test_db_access_layer.py`: backend workspace snapshot coverage for agentic metadata.
- `Docs/v2_phase_19_agentic_workspace_contract.md`: UI and backend snapshot contract.

## Production Readiness Criteria

Phase 19 is releasable when:

- Agentic metadata appears in workspace draft summaries.
- The UI separates candidate authorities from sealed-pack citations.
- Clarification blockers are visible before the preliminary opinion.
- Tool traces show source boundary and status.
- Matter memory shows client facts, adverse material, and missing-evidence tasks.
- Existing reasoning-pack UI remains visible.
- Frontend lint, focused component tests, backend metadata tests, secret scan, and marker scan pass.

## Validation Results

Local targeted validation completed on 2026-05-29:

- Backend workspace metadata test:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_db_access_layer.py::test_db_access_layer_vertical_workflow_rolls_back -q`
  - Result: `1 passed`.
- Frontend component test:
  - Command: `npm --prefix web test -- CaseWorkspace.test.tsx --run`
  - Result: `13 passed`.
- Frontend lint:
  - Command: `npm --prefix web run lint`
  - Result: passed.
- Syntax check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/models.py rag/sl_legal_rag/db/repositories.py`
  - Result: passed.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.
- Detached frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase19-agentic-workspace-frontend`
  - PID: `19148`
  - Log: `logs/test-runs/phase19-agentic-workspace-frontend.log`
  - Result: lint passed, `16` Vitest tests passed, Next build passed, `npm audit` found `0` vulnerabilities, exit `0`.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No official-source web execution.
- No authority promotion execution.
- No new review decision endpoints.
- No final legal advice generation.

## Next Phase

The next step should add review actions for clarification needs and authority-promotion candidates, then connect promoted authority candidates to a sealed-pack expansion workflow.
