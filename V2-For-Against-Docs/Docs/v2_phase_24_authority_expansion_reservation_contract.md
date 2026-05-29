# V2 Phase 24 Authority Expansion Reservation Contract

## Scope

Phase 24 adds a metadata-backed pre-retrieval reservation for authority expansion execution. It prevents duplicate user actions from creating duplicate child packs, without applying a database migration or promoting authorities.

## Reservation Contract

Before `/authority-expansion-plans/{plan_id}/requests/{request_index}/execute` calls the research-pack expansion flow, it must:

- lock the draft row with `SELECT ... FOR UPDATE`;
- validate the plan and request index;
- reject already executed requests;
- reject requests with an active `reserved` or `completed` reservation;
- write an `authority_pack_expansion_reservation.v1` record to the plan metadata.

Reservation records include:

- reservation ID
- request index
- status: `reserved`, `completed`, or `failed`
- reserved user
- reserved timestamp
- request query hash
- child pack ID after completion
- error message after retrieval failure

## Execution Contract

After child pack creation:

- the reserved record is marked `completed`;
- the child pack ID is attached to the reservation;
- the normal execution record is written;
- candidate authorities remain non-citable and unpromoted.

If retrieval fails:

- the reservation is marked `failed`;
- the error message is stored in metadata;
- future retries are allowed because only active `reserved` and `completed` reservations block execution.

## Safety Boundary

This phase remains metadata-only. A later database migration may still add a first-class execution table and uniqueness constraint, but duplicate child-pack creation is now prevented before retrieval in the current metadata architecture.
