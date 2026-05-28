# V2 Phase 7 Deployment Monitoring Contract

## Scope

Phase 7 turns production release, deployment-readiness, hosted-data, and recurring-monitoring steps into a reviewed command manifest and machine-readable reports.

No V1 files, raw corpus data, or database schema are changed.

## Canonical Manifest

The canonical manifest is:

```text
rag/evals/phase7_deployment_monitoring_manifest.json
```

It has four sections:

- `release_gates`: local release evidence that can run without a production stack.
- `deployment_readiness`: checks required before production cutover.
- `hosted_data`: object-storage and corpus-searchability checks.
- `recurring_monitoring`: daily and weekly checks after deployment.

Every manifest command must define:

- `name`
- `command`
- `evidence`

Production-stack commands must set:

- `requires_production_stack: true`

Release-blocking commands must set:

- `required_for_release: true`

## Operational Plan

Render the full plan:

```bash
PYTHONPATH=rag python3 scripts/run_phase7_operational_plan.py --format markdown
```

Render one section as shell:

```bash
PYTHONPATH=rag python3 scripts/run_phase7_operational_plan.py \
  --section deployment_readiness \
  --format shell
```

The renderer does not mutate data. It validates the manifest and produces JSON, Markdown, or shell commands for review and execution.

## Monitoring Snapshot

Plan monitoring without production services:

```bash
PYTHONPATH=rag python3 scripts/run_phase7_monitoring_snapshot.py \
  --output logs/monitoring/phase7-monitoring-plan.json
```

Run local-safe monitoring checks:

```bash
PYTHONPATH=rag python3 scripts/run_phase7_monitoring_snapshot.py \
  --execute \
  --output logs/monitoring/phase7-monitoring-snapshot.json
```

Run production-stack monitoring only after services and environment variables are deliberately supplied:

```bash
PYTHONPATH=rag python3 scripts/run_phase7_monitoring_snapshot.py \
  --execute \
  --include-production-stack \
  --output logs/monitoring/phase7-monitoring-snapshot-prod.json
```

## Deployment Readiness

Before production cutover, the deployment-readiness section must pass on a representative stack:

- schema check
- rollback-only schema smoke
- RAG health with search-index consistency
- real signed load suite

The Phase 7 local release can prove the manifest, plan rendering, and monitoring-report contract. It does not claim production-like load or hosted-data mutation unless those commands are run against a production-like stack.

## Hosted Data Boundary

Phase 7 does not upload raw corpus data to GitHub. Hosted corpus work must use:

- object storage for originals and extracted text assets
- Postgres for durable asset metadata, digests, pages, chunks, packs, and review state
- OpenSearch and Qdrant for derived retrieval indexes
- manifests and reports for reproducibility

## Release Gate

Phase 7 release candidates must pass:

- focused Phase 7 unit tests
- detached backend tests
- detached frontend quality
- detached load-plan gate
- operational-plan render
- monitoring-plan render
- secret scan
- unfinished-marker scan
- Git staging boundary checks

## Safety Boundaries

- Do not commit raw corpus data.
- Do not commit monitoring logs.
- Do not change V1.
- Do not apply a schema migration.
- Do not run hosted-data mutation commands without deliberate production environment setup.
- Do not treat a monitoring plan as production monitoring evidence.
