# V2 Phase 37 Contract: Hosted Capture Acceptance Gate

## Purpose

Phase 37 accepts hosted capture evidence only after the Phase 36 runner has captured evidence, the evidence files are complete and scrubbed, and Phase 34 has validated the backend/DB staging evidence.

This phase does not execute hosted capture. It validates and classifies evidence that already exists under ignored `logs/` paths.

## Implementation Surface

- Manifest: `rag/evals/phase37_hosted_capture_acceptance.json`
- Report builder: `scripts/build_phase37_hosted_capture_acceptance.py`
- Detached gate mode: `hosted-capture-acceptance`
- Report output: `logs/readiness/phase37-hosted-capture-acceptance.json`

## Status Values

- `awaiting_hosted_capture_execution`: Phase 36 has not yet produced `hosted_evidence_captured`.
- `awaiting_captured_evidence_files`: Phase 36 captured evidence, but one or more required evidence files are still missing.
- `awaiting_phase34_backend_db_validation`: captured evidence is present, but Phase 34 has not yet returned `backend_db_staging_validated`.
- `hosted_capture_accepted`: Phase 36 captured evidence, Phase 34 validated it, and all captured evidence is complete and scrubbed.
- `blocked`: a prerequisite failed, captured evidence failed validation, or forbidden hosted-capture content was found.

## Evidence Boundary

Phase 37 validates:

- hosted API health JSON;
- signed workspace smoke log;
- authority workflow smoke log;
- document-source status smoke log;
- read-only DB health JSON;
- DB write guard JSON;
- operator DB acceptance JSON.

## Forbidden Content

Captured evidence must not contain:

- signing headers or body hashes;
- session cookies;
- DB URLs;
- private keys;
- API key labels;
- raw document bodies.

The scanner is intentionally conservative. If it blocks, clean the evidence at the hosted source and rerun Phase 37.

## Exit Criteria

- Local run returns `awaiting_hosted_capture_execution`.
- Hosted run returns `hosted_capture_accepted` only after Phase 36 is `hosted_evidence_captured` and Phase 34 is `backend_db_staging_validated`.
- Missing or failed captured evidence blocks.
- Forbidden content in captured evidence blocks.
- Detached backend tests, frontend quality gate, Phase 37 acceptance gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
