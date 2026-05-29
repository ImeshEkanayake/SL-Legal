# V2 Phase 20 Release: Agentic Review Queue Actions

## Release Goal

Phase 20 makes agentic workflow metadata actionable by adding review queue items for clarification blockers and authority candidates. Lawyers can now see and record review decisions on these items through the existing review workflow.

## Included

- `rag/sl_legal_rag/db/repositories.py`: creates and handles `clarification_need` and `authority_candidate` review items.
- `tests/test_db_access_layer.py`: integration coverage for creation, listing, workspace snapshot, review decisions, and audit events for the new item types.
- `web/src/components/CaseWorkspace.test.tsx`: UI fixture and rendering coverage for the new review items.
- `Docs/v2_phase_20_agentic_review_queue_contract.md`: review queue contract.
- `Docs/v2_codebase_map.md`: Phase 20 code map.

## Production Readiness Criteria

Phase 20 is releasable when:

- Blocking clarification needs create a high-priority `clarification_need` review item.
- Authority candidates create a high-priority `authority_candidate` review item.
- Review queue titles are specific and non-empty.
- Review decisions work for the new item types.
- Audit events are written for the new item types.
- Draft status is not mutated by clarification or authority-candidate decisions.
- Candidate authorities are not promoted by review decisions.
- Existing review item behavior remains green.

## Validation Results

Local targeted validation completed on 2026-05-29:

- Backend review queue integration test:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_db_access_layer.py::test_db_access_layer_vertical_workflow_rolls_back -q`
  - Result: `1 passed`.
- Frontend component test:
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

Detached validation completed on 2026-05-29:

- Backend test suite:
  - Command: `scripts/run_detached_quality_gate.sh tests phase20-agentic-review-queue-tests`
  - Log: `logs/test-runs/phase20-agentic-review-queue-tests.log`
  - Result: `303 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase20-agentic-review-queue-frontend`
  - Log: `logs/test-runs/phase20-agentic-review-queue-frontend.log`
  - Result: ESLint passed, Vitest `16 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No clarification answer persistence.
- No authority candidate promotion execution.
- No official-source web execution.
- No final legal advice generation.

## Next Phase

The next step should implement authority-candidate promotion planning: convert approved candidate review tasks into explicit pack-expansion requests while keeping candidates non-citable until retrieved, anchored, verified, and sealed.
