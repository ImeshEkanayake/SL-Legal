# V2 Phase 42 Runbook: Staging Acceptance Decision

## Purpose

Use this runbook to produce the Phase 42 staging acceptance decision after hosted staging evidence is captured and reviewed.

Phase 42 is a production-planning gate only. It does not authorize production execution.

## Inputs

Required committed inputs:

- `rag/evals/phase42_staging_acceptance_decision.json`
- `Docs/v2_phase_42_staging_acceptance_decision_contract.md`
- Phase 41 manifest, contract, runbook, release note, and builder

Required ignored hosted evidence:

- `logs/readiness/phase33-hosted-staging-validation.json`
- `logs/readiness/phase34-backend-db-staging-validation.json`
- `logs/readiness/phase37-hosted-capture-acceptance.json`
- `logs/readiness/phase38-hosted-capture-execution.json`
- `logs/readiness/phase40-hosted-dry-run-evidence.json`
- `logs/readiness/phase41-hosted-capture-execution-evidence.json`
- `logs/hosted-staging/phase42-lawyer-owner-acceptance.json`
- `logs/hosted-staging/phase42-operator-staging-acceptance.json`
- `logs/hosted-staging/phase42-residual-risk-register.json`

## Local Gate

Run the detached gate:

```bash
scripts/run_detached_quality_gate.sh staging-acceptance-decision phase42-staging-acceptance-decision
```

Expected local status before hosted evidence exists:

```text
awaiting_staging_execution_evidence
```

## Hosted Acceptance Files

Lawyer-owner acceptance shape:

```json
{
  "status": "accepted",
  "reviewed_phase41_evidence": true,
  "lawyer_review_required": true,
  "no_final_legal_advice": true,
  "production_execution_authorized": false
}
```

Operator acceptance shape:

```json
{
  "status": "accepted",
  "reviewed_phase41_evidence": true,
  "db_migration_applied": false,
  "raw_data_uploaded": false,
  "production_execution_authorized": false
}
```

Residual risk register shape:

```json
{
  "status": "accepted",
  "unresolved_blockers": 0,
  "production_execution_authorized": false,
  "lawyer_review_required": true,
  "no_final_legal_advice": true,
  "risks": []
}
```

## Decision Interpretation

- `awaiting_staging_execution_evidence`: run or repair the hosted evidence chain through Phase 41.
- `awaiting_required_acceptance`: collect lawyer-owner acceptance, operator acceptance, or residual risk acceptance.
- `staging_accepted_for_production_planning`: proceed to production cutover planning, not production execution.
- `blocked`: inspect `blockers`, repair evidence, and rerun Phase 42.

## Safety Rules

- Do not commit ignored `logs/` evidence.
- Do not upload raw `data/`.
- Do not include secret values in acceptance files.
- Do not apply a database migration.
- Do not change V1.
- Do not describe any generated report as final legal advice.
