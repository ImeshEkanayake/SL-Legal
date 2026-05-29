# V2 Phase 21 Authority Pack Expansion Planning Contract

## Scope

Phase 21 converts an approved `authority_candidate` review task into an explicit pack-expansion plan. It does not execute retrieval, promote authorities, alter the database schema, touch V1, upload raw data, or change the shared database structure.

## Trigger

When a lawyer approves a review item with:

- `item_type = authority_candidate`
- `decision = approved`

the repository reads the draft metadata, extracts `matter_memory.candidate_authorities`, and creates one `authority_pack_expansion_plan.v1` metadata object for the draft.

## Stored Metadata

The plan is stored in:

- `drafts.metadata.authority_pack_expansion_plans`
- `drafts.metadata.matter_memory.review_state.latest_authority_pack_expansion_plan_id`
- `drafts.metadata.matter_memory.review_state.authority_pack_expansion_status`

The plan contains:

- source review item ID
- parent sealed pack ID
- candidate IDs
- official-source `ResearchPackExpansionRequest` entries
- non-citable boundary marker
- reviewer note explaining that retrieval, anchoring, verification, and sealing are still required

## Safety Rules

- Expansion plans are always `citable = false`.
- Candidate authority status remains unchanged.
- Expansion requests require official-source retrieval.
- Expansion requests use purpose `authority_candidate_pack_expansion`.
- Approval plans retrieval only; it does not cite, seal, or promote the candidate.
- Audit metadata records the generated plan.

## Workspace Visibility

Workspace draft summaries expose `authorityPackExpansionPlans` so the UI can show planned expansion queries beside agentic matter memory.

## Future Phase Boundary

The next phase should execute the planned expansion request through `/v1/research/packs/{pack_id}/expand`, then anchor, verify, and seal any resulting authority before candidate promotion is allowed.
