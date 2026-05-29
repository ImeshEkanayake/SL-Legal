# V2 Phase 18 Release: Agentic Backend Metadata Integration

## Release Goal

Phase 18 connects the Phase 16 agentic research foundation to the backend strategy-draft workflow. Strategy draft generation now produces auditable agentic metadata for tool routing, matter memory, clarification needs, authority candidates, and sealed-pack boundaries.

This is still a safe backend foundation phase: no database migration, no V1 changes, no raw data upload, and no autonomous official-source execution.

## Included

- `rag/sl_legal_rag/agentic_research.py`: deterministic service for building `AgentResearchPlan` and `MatterMemory`.
- `rag/sl_legal_rag/api.py`: `/v1/strategy/draft` builds the agentic bundle after draft validation.
- `rag/sl_legal_rag/db/repositories.py`: `persist_strategy_draft` stores `agentic_research_plan` and `matter_memory` in existing metadata.
- `tests/test_agentic_research_service.py`: deterministic service tests.
- `tests/test_api_research_pack_endpoint.py`: API persistence handoff coverage.
- `tests/test_db_access_layer.py`: draft detail metadata coverage.
- `Docs/v2_phase_18_agentic_backend_metadata_contract.md`: backend metadata contract.

## Production Readiness Criteria

Phase 18 is releasable when:

- Agentic metadata is additive and does not break existing reasoning-pack metadata.
- Tool traces preserve the source boundary between user input, database retrieval, candidate authorities, official-source planning, sealed-pack drafting, and generated review packs.
- Wider authority candidates remain non-citable.
- Matter memory records sealed pack IDs, candidate authorities, adverse material, missing-evidence tasks, clarification needs, and tool traces.
- Draft detail returns structured `agentic_research_plan` and `matter_memory` metadata.
- Existing strategy draft API behavior remains compatible.
- Secret scan and marker scan pass.

## Validation Results

Local targeted validation completed on 2026-05-29:

- Focused service, model, and API tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_agentic_research_models.py tests/test_agentic_research_service.py tests/test_api_research_pack_endpoint.py::test_strategy_draft_endpoint_persists_reviewable_output -q`
  - Result: `11 passed`.
- DB metadata persistence test:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_db_access_layer.py::test_db_access_layer_vertical_workflow_rolls_back -q`
  - Result: `1 passed`.
- Syntax check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/agentic_research.py rag/sl_legal_rag/api.py rag/sl_legal_rag/db/repositories.py`
  - Result: passed.
- Detached test gate:
  - Command: `scripts/run_detached_quality_gate.sh tests phase18-agentic-backend-tests`
  - PID: `18084`
  - Log: `logs/test-runs/phase18-agentic-backend-tests.log`
  - Result: `303 passed`, exit `0`.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers()'`
  - Result: passed.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No official-source web execution.
- No authority promotion execution.
- No UI changes.
- No final legal advice generation.

## Next Phase

The next step should expose the agentic plan and matter memory in the lawyer workspace UI, then add review actions for clarification needs and authority-promotion candidates.
