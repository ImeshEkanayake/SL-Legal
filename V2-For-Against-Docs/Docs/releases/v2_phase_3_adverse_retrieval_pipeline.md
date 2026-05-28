# V2 Phase 3 Release: Adverse Retrieval Pipeline

## Release Goal

Phase 3 makes adverse retrieval a first-class retrieval behavior. V2 now expands every research request into supportive, adverse, limitation, exception, and procedural-risk query variants, records those intents in research pack traces, and evaluates supportive and adverse recall separately.

## Included

- Deterministic for/against query expansion module.
- Intent-tagged OpenSearch and Qdrant candidate retrieval.
- Retrieval trace metadata for query intent, query variant, purpose, and expansion terms.
- Pack item metadata and scoring breakdowns for authority, recency, exactness, adverse relevance, and intent multiplier.
- Retrieval fusion now preserves query intents and query variant IDs across duplicate candidates.
- Evaluation support for separate supportive and adverse recall.
- Fixture and runner for V2 for/against retrieval evaluation.
- Tests proving query expansion, adverse scoring, trace metadata, page-anchor preservation, and separated recall metrics.

## Production Readiness Criteria

Phase 3 is releasable when:

- Query expansion covers supportive, adverse, limitation, exception, and procedural-risk intents.
- Research pack traces expose query intent metadata.
- Selected pack items preserve citation, page anchors, and intent-tagged retrieval evidence.
- Retrieval scoring exposes authority, recency, exactness, and adverse relevance features.
- Evaluation reports supportive and adverse recall separately.
- Blind retrieval fixtures require at least one adverse case.
- Detached backend and frontend quality gates pass.
- No V1 code, raw data, or shared database schema is changed.

## Validation Results

Local validation completed on 2026-05-28:

- Detached backend test run: `logs/test-runs/phase3-tests.log`
  - Result: `229 passed in 0.66s`
  - Exit status: `0`
- Detached frontend quality run: `logs/test-runs/phase3-frontend.log`
  - ESLint: passed
  - Vitest: `2` files passed, `14` tests passed
  - Next.js production build: passed
  - npm audit: `0` vulnerabilities
  - Exit status: `0`
- V2 for/against retrieval fixture gate:
  - Supportive recall: `1.0`
  - Adverse recall: `1.0`
  - Case count: `3`
  - Status: `pass`
- Secret scan: passed.
- Detached runner and V2 retrieval eval script shell syntax checks: passed.
- V2 marker scan for unfinished implementation terms: passed.

## Out of Scope

- No strategy memo prompt changes.
- No claim assessment automation from retrieval results.
- No V2 UI stance panel.
- No database migration execution.
- No raw data upload.
- No change to V1.

## Next Phase

Phase 4 builds the strategy memo and review workflow so generated lawyer-review drafts visibly handle support, adverse, mixed, and context evidence.
