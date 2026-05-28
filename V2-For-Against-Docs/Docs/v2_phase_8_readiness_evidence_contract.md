# V2 Phase 8 Readiness Evidence Contract

## Scope

Phase 8 adds an evidence-backed deployment decision pack. It evaluates the files produced by release gates and production-stack checks, then returns a structured decision.

No V1 files, raw corpus data, or database schema are changed.

## Canonical Requirements

The canonical requirements manifest is:

```text
rag/evals/phase8_deployment_readiness_evidence.json
```

Evidence scopes:

- `local_release`: evidence produced during the current release cycle.
- `production_stack`: evidence produced against a representative production-like stack.

Evidence types:

- `detached_log`: detached gate log with `exit_status=0`.
- `json_status`: JSON report with `status` equal to `passed` or `pass`.
- `load_report`: load-test JSON report with `status` equal to `pass`.
- `searchability_audit`: corpus audit JSON with zero incomplete documents or a passing status.

## Readiness Decisions

The readiness pack can return:

- `ready`: all included required evidence passed.
- `blocked`: required evidence is missing or failed.
- `needs_production_evidence`: reserved for packs where local checks passed but production evidence still needs attachment.

Production deployment is allowed only when the production-stack pack returns `ready`.

## Commands

Build the local release evidence pack:

```bash
PYTHONPATH=rag python3 scripts/run_phase8_readiness_pack.py \
  --output logs/readiness/phase8-readiness-pack.json
```

Build the production-stack pack:

```bash
PYTHONPATH=rag python3 scripts/run_phase8_readiness_pack.py \
  --include-production \
  --output logs/readiness/phase8-readiness-pack-production.json
```

Detached local pack:

```bash
scripts/run_detached_quality_gate.sh readiness-pack phase8-readiness-pack
```

Detached production pack for review, allowing blockers to be recorded:

```bash
scripts/run_detached_quality_gate.sh readiness-pack-production phase8-readiness-pack-production
```

## Required Production Evidence

The production-stack pack requires:

- schema check
- rollback-only schema smoke
- RAG health with search indexes
- Postgres/OpenSearch/Qdrant index consistency
- real signed load suite
- full corpus searchability audit

## Release Gate

Phase 8 release candidates must pass:

- focused Phase 8 tests
- detached backend tests
- detached frontend quality
- detached load-plan gate
- detached readiness-pack gate
- production readiness-pack review that records missing production evidence
- secret scan
- unfinished-marker scan
- Git staging boundary checks

## Safety Boundaries

- Do not commit evidence logs.
- Do not commit raw corpus data.
- Do not change V1.
- Do not apply a database migration.
- Do not mark deployment ready without production-stack evidence.
