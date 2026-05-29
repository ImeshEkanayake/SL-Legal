# V2 Phase 23 Authority Expansion Idempotency Contract

## Scope

Phase 23 fixes the Phase 22 authority expansion execution race found during review. It does not add authority promotion, alter V1, upload raw data, or apply a database migration.

## Locking Contract

`record_authority_pack_expansion_execution` must read the draft row using `SELECT ... FOR UPDATE` before it validates and updates `drafts.metadata.authority_pack_expansion_plans`.

The duplicate request check, execution-record append, plan status update, matter-memory review-state update, and metadata write all occur while the draft row lock is held.

## API Contract

The execution endpoint performs:

1. initial plan validation before retrieval;
2. child pack creation through the existing research-pack expansion flow;
3. locked duplicate re-check before recording execution;
4. `409 Conflict` if the request index was already recorded by another request;
5. execution metadata write and audit event only when the locked re-check is clear.

## Remaining Boundary

This phase makes execution recording safer, but does not implement a pre-retrieval reservation. A concurrent duplicate can still create an unused child pack before receiving `409 Conflict` at the locked recording step. A future DB-backed execution table or reservation record should make execution fully idempotent before expensive retrieval.

## Validation Requirements

- Repository execution recording uses a locked draft read.
- API duplicate re-check runs with `lock_draft = true`.
- Duplicate execution after retrieval returns `409 Conflict`.
- Candidate authorities remain non-citable and unpromoted.
- Existing Phase 22 execution behavior remains green.
