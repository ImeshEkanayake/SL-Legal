# V2 Phase 16 Release: Agentic Research Workflow Foundation

## Release Goal

Phase 16 starts the Maat-informed agentic research workflow step by step. This checkpoint adds production contracts for tool routing, matter memory, clarification needs, authority expansion candidates, and safe authority promotion boundaries.

The phase is intentionally foundational: it makes later backend workflow execution auditable without changing V1, uploading raw data, or applying a database migration.

## Included

- `rag/sl_legal_rag/models.py`: Phase 16 Pydantic contracts for:
  - `AgentToolTrace`
  - `AuthorityExpansionCandidate`
  - `ClarificationNeed`
  - `MatterMemory`
  - `AgentResearchPlan`
- `tests/test_agentic_research_models.py`: focused unit tests for tool routing, trace validation, clarification requirements, authority promotion boundaries, and matter memory.
- `Docs/v2_phase_16_agentic_research_contract.md`: engineering contract for the Phase 16 workflow foundation.
- `Docs/v2_production_product_roadmap.md`: roadmap entry for the Maat-informed workstream.

## Production Readiness Criteria

Phase 16 is releasable when:

- Tool traces are bounded by explicit source boundaries.
- Completed and empty tool traces carry result counts.
- Failed tool traces carry error metadata.
- `answer_from_pack` cannot be planned before database search.
- `official_source_check` cannot be planned before authority expansion.
- Clarification needs require an `ask_clarification` trace.
- Wider authority candidates are not citable until promoted into a sealed pack.
- Promoted candidates require sealed-pack memory.
- Existing Phase 4 reasoning-pack model tests remain green.
- Secret scan and marker scan pass.

## Validation Results

Local targeted validation completed on 2026-05-29:

- Focused Phase 16 and reasoning model tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with eval-type-backport python -m pytest tests/test_agentic_research_models.py tests/test_reasoning_pack_models.py -q`
  - Result: `13 passed`.
- Detached test gate:
  - Command: `scripts/run_detached_quality_gate.sh tests phase16-agentic-research-tests`
  - PID: `17072`
  - Log: `logs/test-runs/phase16-agentic-research-tests.log`
  - Result: `301 passed`, exit `0`.
- Detached backend gate:
  - Command: `scripts/run_detached_quality_gate.sh backend phase16-agentic-research-backend`
  - PID: `16993`
  - Log: `logs/test-runs/phase16-agentic-research-backend.log`
  - Result: blocked before test execution because local Docker service `rag-postgres` was not running.
- Syntax check:
  - Command: `python3 -m py_compile rag/sl_legal_rag/models.py`
  - Result: passed.
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
- No autonomous web/official-source execution.
- No backend API route changes yet.
- No UI changes yet.
- No final legal advice generation.

## Next Phase

The next implementation step should add the backend service layer that creates and persists `AgentResearchPlan` and `MatterMemory` inside existing draft or agent metadata fields, then connects it to offline validation before any UI expansion.
