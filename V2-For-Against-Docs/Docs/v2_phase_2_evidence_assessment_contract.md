# V2 Phase 2 Evidence Assessment Contract

## Purpose

Phase 2 makes support, adverse, mixed, and context evidence a typed claim-level contract. The canonical unit is not a whole document. It is one research pack item assessed against one legal claim.

## Stance Values

- `supports_claim`: the source materially supports the claim.
- `contradicts_claim`: the source weakens, limits, contradicts, or creates risk for the claim.
- `mixed`: the source helps on one part of the claim and hurts on another; a rationale is mandatory.
- `context`: the source is useful background but does not materially prove or weaken the claim.

## API Contract

Create an assessment:

```http
POST /v1/cases/{case_id}/evidence/assessments
```

Request body:

```json
{
  "claim_text": "The employer refused to bargain with a qualifying trade union.",
  "pack_id": "pack_123",
  "pack_item_id": "pack_123_item_001",
  "stance": "contradicts_claim",
  "rationale": "The source is adverse because the duty depends on qualification.",
  "confidence_score": 0.74,
  "risk_level": "high",
  "source_quote": "qualifying trade union",
  "page_start": 1,
  "page_end": 1
}
```

List grouped assessments:

```http
GET /v1/cases/{case_id}/evidence/assessments?pack_id=pack_123
```

Response groups are ordered as support, adverse, mixed, then context. Each item includes the claim, pack item, stance, rationale, quote, citation, page range, source endpoint, review status, and source metadata.

## Persistence Contract

Phase 2 does not apply a database migration. It uses the existing reviewed tables:

- `legal_claims`: stores the claim and V2 evidence assessment metadata in `metadata.evidence_assessments`.
- `legal_claim_citations`: stores the claim-to-pack-item link with a stance-derived `citation_role`.
- `research_pack_items` and `retrieval_chunks`: supply source, citation, document, page, and quote context.

Stance-to-role mapping:

| Stance | Citation Role |
| --- | --- |
| `supports_claim` | `support` |
| `contradicts_claim` | `adverse` |
| `mixed` | `mixed` |
| `context` | `context` |

This preserves compatibility with V1-style supported claims while allowing one pack item to support one claim and contradict another.

## Validation Rules

- A request must provide either `claim_id` or `claim_text`.
- `pack_id` and `pack_item_id` are required.
- `confidence_score` must be between `0` and `1`.
- `page_end` must be greater than or equal to `page_start` when both are present.
- `mixed` evidence requires a non-empty rationale.
- The pack item must exist inside the supplied research pack.
- Existing claim assessments must belong to the requested case and pack.

## Review and Audit

Creating an assessment writes an `evidence.assessment.recorded` audit event. The current review status is inherited from the claim review item when available. Dedicated assessment-level review rows are part of the reviewed migration plan.

## Migration Plan

Before Phase 4 persistence work, review and apply a migration that introduces:

- `claim_evidence_assessments`
  - `assessment_id`
  - `case_id`
  - `claim_id`
  - `pack_id`
  - `pack_item_id`
  - `stance`
  - `rationale`
  - `confidence_score`
  - `risk_level`
  - `source_quote`
  - `page_start`
  - `page_end`
  - `review_status`
  - timestamps and reviewer columns
- Indexes on `(case_id, stance)`, `(claim_id, stance)`, and `(pack_id, pack_item_id)`.
- A foreign key to `review_items` or a dedicated assessment review target.
- A backfill from `legal_claims.metadata.evidence_assessments` and `legal_claim_citations`.

No migration is applied in Phase 2 because the shared database remains protected.
