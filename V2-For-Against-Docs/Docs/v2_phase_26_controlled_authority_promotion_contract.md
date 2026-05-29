# V2 Phase 26 Contract: Controlled Authority Promotion

## Purpose

Phase 26 promotes verified authority expansion child-pack items into citable matter-memory references. It is the first phase that can make an authority candidate citable, and only after execution and verification have already succeeded.

## API Contract

`POST /v1/cases/{case_id}/drafts/{draft_id}/authority-expansion-plans/{plan_id}/child-packs/{child_pack_id}/promote`

Request body:

- `pack_item_ids`: optional list of verified child-pack item IDs. If omitted, all verified items in the child pack are promoted.
- `reviewer_note`: required note for the promotion record, with a safe default.

The endpoint:

- requires signed authentication and case permission;
- rejects child packs that were not executed and verified;
- rejects partially verified or needs-review child packs;
- rejects unknown, unanchored, or unverified pack item IDs;
- writes an `authority_pack_promotion.v1` record into the expansion plan metadata;
- updates `matter_memory.candidate_authorities` to `promoted_to_sealed_pack`;
- records an `authority_pack_expansion.promoted` audit event.

## Promotion Rules

Promotion is allowed only when:

- the child pack has an execution record;
- the child pack has a matching `authority_pack_verification.v1` record;
- the verification record status is `verified`;
- every promoted item has source anchors, citation metadata, and no unresolved verification issues;
- the child pack hash matches the execution and verification records.

## Citable Boundary

Promotion records are citable. Expansion plans and verification records remain historical controls and are not themselves cited.

After promotion:

- `matter_memory.sealed_pack_ids` includes the child pack;
- matching authority candidates carry `promoted_pack_item_ids`;
- matching authority candidates become `promoted_to_sealed_pack`;
- `matter_memory.review_state.authority_candidates_are_citable` is true.

## Persistence Boundary

No database migration is used. Promotion records are stored in existing draft metadata under the expansion plan.

## Out Of Scope

- No V1 changes.
- No raw data upload.
- No database migration.
- No automatic final legal advice generation.
