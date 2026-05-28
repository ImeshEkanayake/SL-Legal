# V2 Phase 8 Readiness Runbook

## Local Release Evidence

1. Run detached backend tests:

```bash
scripts/run_detached_quality_gate.sh tests phase8-tests
```

2. Run detached frontend quality:

```bash
scripts/run_detached_quality_gate.sh frontend phase8-frontend
```

3. Run detached load-plan:

```bash
scripts/run_detached_quality_gate.sh load-plan phase8-load-plan
```

4. Build the local readiness pack:

```bash
scripts/run_detached_quality_gate.sh readiness-pack phase8-readiness-pack
```

Expected local decision:

```text
ready
```

## Production-Stack Evidence

Before production cutover, collect:

```bash
PYTHONPATH=rag python scripts/check_postgres_schema.py > logs/readiness/schema-check.json
PYTHONPATH=rag python scripts/smoke_test_postgres_schema.py > logs/readiness/schema-smoke.json
PYTHONPATH=rag python scripts/check_rag_production_health.py --require-search-indexes > logs/readiness/rag-health.json
PYTHONPATH=rag python scripts/check_rag_index_consistency.py > logs/readiness/index-consistency.json
scripts/run_detached_quality_gate.sh load phase8-load
PYTHONPATH=rag python scripts/audit_full_corpus_searchability.py > logs/readiness/searchability-audit.json
```

Then build:

```bash
scripts/run_detached_quality_gate.sh readiness-pack-production phase8-readiness-pack-production
```

Expected production decision:

```text
ready
```

If the decision is `blocked`, review the `blockers` array in:

```text
logs/readiness/phase8-readiness-pack-production.json
```

## Review Rules

- A local `ready` decision means the release package is internally validated.
- A production `ready` decision means cutover evidence is complete.
- Missing production-stack reports block production deployment.
- Failed schema, health, index, load, or searchability reports block deployment.
- Evidence logs remain local or release artifacts; they are not committed to normal Git.

## Recovery

For missing evidence:

1. Run the named check.
2. Confirm the output path matches `rag/evals/phase8_deployment_readiness_evidence.json`.
3. Rebuild the readiness pack.

For failed evidence:

1. Fix the failed subsystem.
2. Rerun that check.
3. Rerun related checks if the fix touches shared infrastructure.
4. Rebuild the readiness pack.
