# V2 Phase 22 Authority Pack Expansion Execution Contract

## Scope

Phase 22 executes a planned authority pack-expansion request through the existing research-pack expansion flow. It records the child pack in draft metadata, but does not promote candidate authorities, cite them as law, alter the database schema, touch V1, or upload raw data.

## API Contract

Endpoint:

`POST /v1/cases/{case_id}/drafts/{draft_id}/authority-expansion-plans/{plan_id}/requests/{request_index}/execute`

Behavior:

- requires signed authenticated case access;
- loads the draft-scoped `authority_pack_expansion_plan.v1`;
- rejects missing plans, missing request indexes, and duplicate request execution;
- converts the selected planned request to a parent-linked `ResearchQueryRequest`;
- executes the existing research-pack expansion path;
- stores the resulting child pack through existing research-pack persistence;
- records the child pack ID, hash, item count, execution user, execution timestamp, and request query hash back into the expansion plan;
- writes an `authority_pack_expansion.executed` audit event.

## Metadata Contract

Executed plans remain in:

- `drafts.metadata.authority_pack_expansion_plans`

Each execution appends:

- `executed_pack_ids`
- `execution_records`
- `status = partially_executed` until every request is executed
- `status = executed` after all planned requests have child packs

`drafts.metadata.matter_memory.review_state` also records:

- `authority_candidates_are_citable = false`
- latest expansion plan ID
- expansion status
- latest child pack ID

## Safety Rules

- Execution does not promote candidate authorities.
- Execution does not set `citable = true`.
- Execution does not create final legal advice.
- Duplicate execution of the same request index is rejected.
- Child packs are still not usable as cited legal authority until source anchoring, authority verification, and sealing checks pass in later phases.

## Future Phase Boundary

The next phase should inspect the child pack, anchor returned sources, verify authority metadata, and only then allow controlled candidate promotion into sealed-pack citations.
