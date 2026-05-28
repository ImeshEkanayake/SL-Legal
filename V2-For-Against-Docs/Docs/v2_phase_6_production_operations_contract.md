# V2 Phase 6 Production Operations Contract

## Scope

Phase 6 makes V2 deployable and operable. It ties together load testing, metrics, health checks, release gates, incident response, data hydration, index rebuilds, and corpus quality audits.

No V1 files, raw corpus data, or database schema are changed.

## Load Testing

The canonical load scenario file is:

```text
rag/evals/phase6_load_scenarios.json
```

It covers:

- workspace snapshot
- research pack creation
- strategy validation
- source viewer
- review queue

Run a scenario plan without HTTP traffic:

```bash
scripts/run_detached_quality_gate.sh load-plan phase6-load-plan
```

Run the real load suite against a local or staging API:

```bash
SL_LEGAL_API_BASE_URL=http://127.0.0.1:8000 \
SL_LEGAL_LOAD_TEST_USER_ID=<user_id> \
SL_LEGAL_AUTH_HMAC_SECRET=<32+ char secret> \
SL_LEGAL_LOAD_TEST_CASE_ID=<case_id> \
SL_LEGAL_LOAD_TEST_PACK_ID=<pack_id> \
SL_LEGAL_LOAD_TEST_PACK_ITEM_ID=<pack_item_id> \
scripts/run_detached_quality_gate.sh load phase6-load
```

The runner writes:

```text
logs/load-tests/phase6-load-report.json
```

That report includes per-scenario p50, p95, p99, max latency, error rate, threshold status, and slow/error samples.

## Service-Level Targets

Initial local-stack targets:

- workspace snapshot p95 <= 750 ms
- research pack creation p95 <= 8,000 ms
- strategy validation p95 <= 1,000 ms
- source viewer p95 <= 1,500 ms
- review queue p95 <= 750 ms
- error rate = 0 for release scenarios

These targets are intentionally stricter for read paths and bounded for generation/retrieval paths.

## Observability

The API exposes operational metrics at:

- `/v1/operations/metrics`
- `/v1/operations/metrics/prometheus`

Access:

- signed API auth for JSON metrics
- `SL_LEGAL_METRICS_BEARER_TOKEN` for Prometheus scrape access

Metrics include:

- HTTP request counts
- HTTP error counts
- request latency summaries
- request-body guardrail rejections
- rate-limit guardrail rejections
- audit-write failures

Release review must also inspect domain metrics from:

- `scripts/check_rag_production_health.py`
- `scripts/run_production_benchmark_gates.py`
- `scripts/run_v2_for_against_retrieval_eval.py`
- `scripts/run_phase6_load_tests.py`

## Release Gate

Phase 6 release candidates must pass:

- detached backend tests
- detached frontend quality
- secret scan
- compile check
- unfinished-marker scan
- load scenario contract tests
- load-plan dry run
- workspace browser verification when UI files changed, and before production deployment
- no raw data, logs, `.next`, `node_modules`, `.env.azure-openai`, or large files in Git staging

For production deployment, also run against a production-like stack:

- schema check
- rollback-only schema smoke test
- RAG production health
- benchmark gate
- real Phase 6 load suite
- adverse retrieval evaluation

## Runbooks

Core operational runbooks:

- `Docs/v2_phase_6_operations_runbook.md`: release, load, metrics, incident, rollback, and audit workflow.
- `Docs/object_storage_asset_sync_runbook.md`: corpus asset hydration and index rebuild workflow.
- `Docs/v2_engineering_testing_playbook.md`: detached gate and quality rules.
- `Docs/v2_phase_6_production_operations_contract.md`: Phase 6 operational contract.

## Safety Boundaries

- Do not commit raw corpus data.
- Do not commit load-test logs.
- Do not change V1.
- Do not run schema migrations without a reviewed migration plan.
- Do not treat a passing load plan as a real load result; it only validates scenario configuration.
- Do not publish a production release without real load evidence from a representative stack.
