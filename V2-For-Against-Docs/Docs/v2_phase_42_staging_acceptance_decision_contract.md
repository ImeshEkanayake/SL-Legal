# V2 Phase 42 Contract: Staging Acceptance Decision

## Purpose

Phase 42 converts hosted staging evidence into a controlled production-planning decision.

This phase does not execute production traffic, upload raw data, change V1, or apply a database migration. It consumes ignored `logs/` evidence and decides whether staging is ready for production cutover planning.

## Implementation Surface

- Manifest: `rag/evals/phase42_staging_acceptance_decision.json`
- Decision builder: `scripts/build_phase42_staging_acceptance_decision.py`
- Detached gate mode: `staging-acceptance-decision`
- Report output: `logs/readiness/phase42-staging-acceptance-decision.json`

## Status Values

- `awaiting_staging_execution_evidence`: Phase 41 or earlier hosted evidence is not yet fully validated.
- `awaiting_required_acceptance`: hosted evidence is validated, but lawyer-owner acceptance, operator acceptance, or residual risk acceptance is not present.
- `staging_accepted_for_production_planning`: hosted evidence, required acceptance, and residual risk checks are verified.
- `blocked`: prerequisites failed, evidence failed validation, required fields mismatched, forbidden content was found, or unresolved blockers remain.

## Decision Values

- `wait_for_hosted_evidence`
- `wait_for_acceptance`
- `go_for_production_planning`
- `blocked`

## Evidence Boundary

Phase 42 validates:

- Phase 33 hosted staging validation;
- Phase 34 backend DB staging validation;
- Phase 37 hosted capture acceptance;
- Phase 38 hosted capture execution;
- Phase 40 hosted dry-run evidence;
- Phase 41 hosted capture execution evidence;
- lawyer-owner staging acceptance;
- operator staging acceptance;
- residual risk register.

## Required Acceptance

Lawyer-owner acceptance must confirm:

- Phase 41 evidence was reviewed;
- lawyer review remains required;
- the report is not final legal advice;
- production execution is not authorized.

Operator acceptance must confirm:

- Phase 41 evidence was reviewed;
- no database migration was applied;
- no raw data was uploaded;
- production execution is not authorized.

Residual risk acceptance must confirm:

- unresolved blockers are zero;
- lawyer review remains required;
- the report is not final legal advice;
- production execution is not authorized.

## Forbidden Content

Staging acceptance evidence must not contain:

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

- Local detached run returns `awaiting_staging_execution_evidence` until hosted evidence exists.
- Staging can be accepted for production planning only after Phase 41 returns `hosted_capture_execution_evidence_validated`.
- Missing owner, operator, or risk acceptance returns `awaiting_required_acceptance`.
- Any DB migration, raw data upload, production authorization, unresolved blocker, or forbidden content blocks.
- Detached backend tests, frontend quality gate, Phase 42 gate, secret scan, and marker scan pass.
- No V1 changes, raw data upload, database migration, production mutation, or raw data staging.
