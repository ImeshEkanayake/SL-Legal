# V2 Phase 5 Release: Production Reasoning UI

## Release Goal

Phase 5 gives lawyers a production workspace for the Phase 4 reasoning pack. The UI now exposes the preliminary opinion, issue matrix, legal elements, fact-to-law mapping, for/against brief, missing evidence, authority verification, pack citations, and review decisions in one case workspace.

## Included

- Workspace snapshot contract now surfaces `requestedOutput` and `reasoningPack` from draft metadata.
- Reasoning view added to the source/workspace navigation.
- Reasoning pack detail page for:
  - preliminary opinion
  - issue matrix
  - for/against analysis
  - fact-to-law mapping
  - missing evidence
  - authority verification
- Pack item citation buttons open the research pack evidence view.
- Review decision server action and API client.
- Review queue actions for approve, request changes, and reject.
- UI tests for reasoning navigation, citation navigation, and reviewer decisions.
- Backend integration assertion for reasoning-pack metadata in workspace snapshot.
- Phase 5 UI contract documentation.

## Production Readiness Criteria

Phase 5 is releasable when:

- Reasoning-pack data is available in the workspace snapshot without a schema migration.
- Lawyers can inspect issue, law, fact, application, risk, opinion, missing evidence, and next-review items.
- Source pack citations navigate back to pack evidence.
- Review decisions use the existing signed backend endpoint and audit path.
- Empty and non-reasoning drafts remain readable as draft previews.
- Detached backend and frontend quality gates pass.
- Browser verification confirms the local workspace renders.
- No V1 code, raw data, or database schema is changed.

## Validation Results

Local targeted validation completed on 2026-05-28:

- Frontend targeted test:
  - Command: `npm --prefix web run test -- CaseWorkspace.test.tsx`
  - Result: `13` tests passed
- Backend targeted tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with pydantic-settings --with fastapi --with httpx --with pypdfium2 --with eval-type-backport python -m pytest tests/test_db_access_layer.py tests/test_api_research_pack_endpoint.py::test_workspace_snapshot_endpoint_returns_case_ui_contract -q`
  - Result: `2 passed`
- Frontend lint: passed.
- Frontend production build: passed.

- Detached backend test run: `logs/test-runs/phase5-tests.log`
  - Result: `238 passed in 0.83s`
  - Exit status: `0`
- Detached frontend quality run: `logs/test-runs/phase5-frontend-rerun.log`
  - ESLint: passed
  - Vitest: `2` files passed, `16` tests passed
  - Next.js production build: passed
  - npm audit: `0` vulnerabilities
  - Exit status: `0`
- Secret scan: passed.
- Compile check: passed.
- Marker scan for unfinished implementation terms: passed.
- Browser verification:
  - Local URL: `http://127.0.0.1:3000`
  - Result: workspace rendered and right-rail reasoning navigation displayed without label overlap.

## Out of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No new model prompting behavior.
- No automated legal approval.

## Next Phase

Phase 6 hardens production operations with load testing, observability, release runbooks, and production-like deployment checks.
