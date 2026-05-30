# V2 Phase 43 Contract: Production Cutover Readiness Pack

## Purpose

Phase 43 gathers the evidence needed before a production cutover dry run can be planned.

This phase is non-mutating. It does not execute production traffic, apply a database migration, upload raw data, sign release artifacts, or change V1.

## Implementation Surface

- Manifest: `rag/evals/phase43_production_cutover_readiness.json`
- Readiness builder: `scripts/build_phase43_production_cutover_readiness.py`
- Detached gate mode: `production-cutover-readiness`
- Detached environment gate mode: `production-cutover-readiness-env`
- Report output: `logs/readiness/phase43-production-cutover-readiness.json`

## Status Values

- `awaiting_staging_acceptance`: Phase 42 has not returned `staging_accepted_for_production_planning`.
- `awaiting_production_readiness_evidence`: staging is accepted, but production-readiness evidence or rollback evidence is missing.
- `awaiting_production_environment_inventory`: evidence is complete, but production environment variables have not been inspected through the secret-safe environment gate.
- `ready_for_production_cutover_dry_run`: evidence, rollback readiness, incident readiness, and environment inventory are verified.
- `blocked`: prerequisites failed, evidence failed validation, required fields mismatched, forbidden content was found, or required environment values were invalid.

## Evidence Boundary

Phase 43 validates:

- Phase 42 staging acceptance;
- release provenance for the Phase 42 tag;
- signing plan for the Phase 42 tag;
- schema readiness without migration;
- rollback-only schema smoke evidence;
- RAG and index health;
- signed load-suite evidence;
- corpus searchability evidence;
- rollback checklist;
- incident-response checklist;
- production environment inventory.

## Environment Boundary

Environment validation records only:

- whether each value is present;
- whether secret values meet minimum length;
- whether URL values have an HTTP(S) scheme;
- whether expected fixed values match.

Secret values are never written to the report.

## Authorization Boundary

Phase 43 may authorize only Phase 44 dry-run planning.

The report must keep:

- `production_execution_authorized=false`
- `production_mutation_authorized=false`
- `database_migration_authorized=false`
- `raw_data_upload_authorized=false`
- `lawyer_review_required=true`
- `no_final_legal_advice=true`

## Forbidden Content

Readiness evidence must not contain:

- signing secrets;
- signed auth headers or body-hash headers;
- session cookies;
- bearer tokens;
- DB URLs;
- private keys;
- raw document bodies;
- raw response bodies;
- final legal advice language.

## Exit Criteria

- Local detached run returns `awaiting_staging_acceptance` until Phase 42 is accepted.
- Production readiness cannot pass without Phase 42 acceptance, provenance, signing plan, rollback evidence, incident readiness, and environment inventory.
- Any production execution, production mutation, DB migration, raw data upload, signing execution approval, or forbidden content blocks.
- Detached backend tests, frontend quality gate, Phase 43 gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, production mutation, or raw data staging.
