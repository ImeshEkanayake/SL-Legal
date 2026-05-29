# V2 Phase 34 Contract: Real Backend and DB Staging Validation

## Purpose

Phase 34 validates that hosted staging is connected to the real V2 backend and a controlled staging DB path before any production cutover work continues.

This phase is evidence-only. It does not upload raw data, duplicate the corpus, migrate the database, or perform write traffic against the shared DB.

## Implementation Surface

- Manifest: `rag/evals/phase34_backend_db_staging_validation.json`
- Report builder: `scripts/build_phase34_backend_db_staging_validation.py`
- Detached gate mode: `backend-db-staging-validation`
- Report output: `logs/readiness/phase34-backend-db-staging-validation.json`

## Status Values

- `awaiting_backend_db_staging_evidence`: all local prerequisites are present, but real hosted backend/DB evidence is not complete.
- `backend_db_staging_validated`: all required hosted staging evidence is present and verified.
- `blocked`: a prerequisite is missing, hosted evidence failed, or DB safety fields do not prove a read-only/no-write state.

## Required Evidence

Phase 34 requires:

- Phase 33 hosted staging validation report.
- Hosted API health evidence showing runtime `hosted_staging`, backend `real`, and DB connectivity.
- Signed workspace API smoke log with `exit_status=0`.
- Read-only DB health evidence showing `access_mode=read_only` and no migration applied.
- DB write guard evidence showing `write_count=0`, `migration_count=0`, and `raw_data_uploaded=false`.
- Authority workflow smoke log against the real backend with `exit_status=0`.
- Document source viewer smoke log against the real backend with `exit_status=0`.
- Operator DB acceptance showing no migration, no raw data upload, and write review completed.

## Validation Rules

- Missing hosted evidence is pending, not successful.
- A nonzero write count blocks the phase even if the evidence status text says it passed.
- A migration count above zero blocks the phase.
- Raw data upload evidence set to true blocks the phase.
- Phase 33 can remain pending locally, but Phase 34 cannot validate until Phase 33 is `hosted_staging_validated`.
- Evidence files must stay under ignored `logs/` paths and must not contain secrets.

## Exit Criteria

- Local run returns `awaiting_backend_db_staging_evidence` until hosted evidence is attached.
- Hosted run returns `backend_db_staging_validated` only after all required evidence is verified.
- Detached backend tests, frontend quality gate, Phase 34 validation gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
