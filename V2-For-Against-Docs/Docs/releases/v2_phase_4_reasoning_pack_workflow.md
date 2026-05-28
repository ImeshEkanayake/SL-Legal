# V2 Phase 4 Release: Reasoning Pack and Preliminary Opinion Workflow

## Release Goal

Phase 4 turns the retrieval pack into a production lawyer-review reasoning layer. The system now generates structured authority verification, issue matrix, legal element matrix, fact-to-law mapping, for/against brief, missing evidence checklist, preliminary opinion, and lawyer review pack output while staying bounded to the sealed research pack.

## Included

- Roadmap updated to formally adopt the hybrid workstream from `detailed.md`.
- Structured Pydantic models for the reasoning pack and preliminary opinion workflow.
- Strategy prompt contract for `for_against_brief`, `preliminary_legal_opinion`, and `lawyer_review_pack`.
- Citation validation for reasoning-pack pack item IDs.
- Cautious-language and lawyer-verification validators.
- Draft persistence of `metadata.reasoning_pack` and `metadata.requested_output`.
- Review queue entries for adverse reasoning and missing evidence.
- API response support for `reasoning_review_item_ids`.
- Unit and integration tests for schemas, validators, generation, persistence, draft detail metadata, and review queue behavior.
- Phase 4 contract documentation.

## Production Readiness Criteria

Phase 4 is releasable when:

- Requested reasoning outputs require a structured `reasoning_pack`.
- Legal citations are limited to the sealed research pack.
- Uncited legal claim sentences are rejected.
- Outcome-guarantee wording is rejected.
- Unverified propositions remain marked for lawyer verification.
- Missing evidence entries exist for incomplete facts, documents, case law, procedure, or authority verification.
- Draft detail returns structured reasoning metadata.
- Review queue includes draft, legal claim, adverse reasoning, and missing-evidence review items.
- Detached backend and frontend quality gates pass.
- Secret scan and marker scan pass.
- No V1 code, raw data, or database schema is changed.

## Validation Results

Local validation completed on 2026-05-28:

- Targeted Phase 4 backend tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with pydantic-settings --with fastapi --with httpx --with pypdfium2 --with eval-type-backport python -m pytest tests/test_reasoning_pack_models.py tests/test_strategy_reasoning.py tests/test_api_research_pack_endpoint.py::test_strategy_draft_endpoint_persists_reviewable_output tests/test_db_access_layer.py -q`
  - Result: `18 passed in 0.45s`

- Detached backend test run: `logs/test-runs/phase4-tests-rerun.log`
  - Result: `238 passed in 0.72s`
  - Exit status: `0`
- Detached frontend quality run: `logs/test-runs/phase4-frontend.log`
  - ESLint: passed
  - Vitest: `2` files passed, `14` tests passed
  - Next.js production build: passed
  - npm audit: `0` vulnerabilities
  - Exit status: `0`
- Secret scan: passed.
- Compile check: passed.
- Marker scan for unfinished implementation terms: passed.

## Out of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No production UI screen changes.
- No automated lawyer approval.

## Next Phase

Phase 5 builds the production UI for inspecting the reasoning pack, adverse reasoning, missing evidence, source anchors, and lawyer review decisions.
