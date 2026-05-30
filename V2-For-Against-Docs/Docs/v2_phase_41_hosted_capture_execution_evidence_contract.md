# V2 Phase 41 Contract: Hosted Capture Execution Evidence

## Purpose

Phase 41 validates the evidence produced by a hosted Phase 38 capture execution.

This phase does not execute hosted capture. It consumes ignored `logs/` evidence and classifies whether capture is still waiting, captured but pending backend/DB validation, captured but pending acceptance, fully validated, or blocked.

## Implementation Surface

- Manifest: `rag/evals/phase41_hosted_capture_execution_evidence.json`
- Evidence builder: `scripts/build_phase41_hosted_capture_execution_evidence.py`
- Detached gate mode: `hosted-capture-execution-evidence`
- Report output: `logs/readiness/phase41-hosted-capture-execution-evidence.json`

## Status Values

- `awaiting_hosted_dry_run_validation`: Phase 40 has not yet returned `hosted_dry_run_validated`.
- `awaiting_hosted_capture_execution`: Phase 40 is valid, but Phase 38/Phase 36 execution evidence is not yet captured.
- `hosted_capture_executed_pending_backend_db_validation`: Phase 36 captured evidence, but Phase 34 is not yet `backend_db_staging_validated`.
- `hosted_capture_executed_pending_acceptance`: backend/DB validation passed, but Phase 37 has not yet accepted the capture.
- `hosted_capture_execution_evidence_validated`: Phase 36 captured evidence, Phase 34 validated it, Phase 37 accepted it, and all captured evidence is complete and scrubbed.
- `blocked`: prerequisites failed, evidence failed validation, captured evidence is missing after Phase 36 captured it, or forbidden hosted content was found.

## Evidence Boundary

Phase 41 validates:

- Phase 40 dry-run evidence report;
- Phase 38 execution report;
- Phase 36 capture-run report;
- Phase 34 backend/DB validation report;
- Phase 37 capture acceptance report;
- hosted API health JSON;
- signed workspace, authority workflow, and document-source smoke logs;
- DB read-only health, DB write guard, and operator DB acceptance JSON.

## Required Execution Proof

Phase 38 execution evidence must show:

- `execute=true`
- `environment_included=true`
- `summary.phase36_status=hosted_evidence_captured`
- `summary.captured_evidence=7`
- `summary.blockers=0`

Phase 36 capture evidence must show:

- `execute=true`
- `environment_included=true`
- `summary.captured_evidence=7`
- `summary.failed_captures=0`
- `summary.blockers=0`

## Forbidden Content

Execution evidence must not contain:

- signing secrets;
- signed auth headers or body-hash headers;
- session cookies;
- bearer tokens;
- DB URLs;
- private keys;
- API key labels;
- raw document bodies;
- raw response bodies.

## Exit Criteria

- Local detached run returns `awaiting_hosted_dry_run_validation`.
- Hosted execution evidence can validate only after Phase 40, Phase 38, Phase 36, Phase 34, and Phase 37 evidence pass.
- Any DB migration, raw data upload, unintended domain write, missing captured evidence, or forbidden hosted content blocks.
- Detached backend tests, frontend quality gate, Phase 41 gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
