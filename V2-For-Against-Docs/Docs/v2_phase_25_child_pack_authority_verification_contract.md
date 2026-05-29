# V2 Phase 25 Contract: Child Pack Source Anchoring and Authority Verification

## Purpose

Phase 25 verifies executed authority expansion child packs before any candidate authority can be promoted or cited.

## API Contract

`POST /v1/cases/{case_id}/drafts/{draft_id}/authority-expansion-plans/{plan_id}/child-packs/{child_pack_id}/verify`

The endpoint:

- requires signed authentication and case permission;
- verifies the child pack was already recorded by the authority expansion execution phase;
- reloads the persisted child pack and checks its canonical hash against the execution record;
- inspects each pack item through the existing pack item source and source-anchor path;
- writes an `authority_pack_verification.v1` record into `drafts.metadata.authority_pack_expansion_plans`;
- records an `authority_pack_expansion.verified` audit event.

## Verification Rules

An authority item is `verified` only when:

- it has at least one source anchor;
- it has a citation;
- it is a primary or high-authority legal material level already supported by the retrieval metadata;
- it has no unresolved verification issues.

Otherwise it is marked `requires_lawyer_review`.

## Promotion Boundary

Verification is not promotion. Every Phase 25 record keeps:

- `citable: false`;
- `promotion_boundary: verification_only_not_promoted`;
- `authority_candidates_are_citable: false` in draft review state.

Candidate authorities remain non-citable until a later controlled promotion phase seals them for legal use.

## Persistence Boundary

No database migration is used. Verification records are stored in existing draft metadata under the existing expansion plan object.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No authority promotion.
- No final legal advice language.
