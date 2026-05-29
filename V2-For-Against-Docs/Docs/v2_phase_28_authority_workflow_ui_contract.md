# V2 Phase 28 Contract: Authority Workflow UI Integration

## Purpose

Phase 28 connects the lawyer workspace UI to the existing authority expansion workflow so a reviewer can execute planned authority searches, verify child packs, and promote verified authorities without leaving the reasoning panel.

## Scope

This phase is a UI and server-action integration over existing backend capabilities:

- authority expansion request execution;
- child-pack source anchoring and verification;
- controlled promotion of verified authority items.

It does not change V1, upload raw data, apply a database migration, or make unverified candidate authorities citable.

## UI Workflow

1. The reasoning panel shows each authority expansion plan and planned request.
2. `Execute` calls the backend request-execution endpoint and displays the created child pack.
3. `Verify` calls the child-pack verification endpoint for an executed pack.
4. Verification records display anchor counts, verification status, review counts, and citable boundary.
5. `Promote` is enabled only after the child pack verifies successfully.
6. Promotion sends verified pack item IDs that do not require lawyer review.
7. Promotion records display promoted count, authority item metadata, and citable state.

## API Boundary

The frontend calls the existing signed backend endpoints through server actions:

- `POST /v1/cases/{case_id}/drafts/{draft_id}/authority-expansion-plans/{plan_id}/requests/{request_index}/execute`
- `POST /v1/cases/{case_id}/drafts/{draft_id}/authority-expansion-plans/{plan_id}/child-packs/{child_pack_id}/verify`
- `POST /v1/cases/{case_id}/drafts/{draft_id}/authority-expansion-plans/{plan_id}/child-packs/{child_pack_id}/promote`

Server actions revalidate the workspace after successful calls. The client also updates local draft-plan state immediately so the reviewer sees action progress without waiting for a full reload.

## Safety Rules

- Candidate authorities remain non-citable until the promotion endpoint returns a citable promotion record.
- Verification status must be shown separately from promotion status.
- Promotion must not include items marked `requires_lawyer_review`.
- The UI must not imply final legal advice; it remains a lawyer-review workflow.
- Backend validation remains authoritative for idempotency, reservations, hash checks, and promotion eligibility.

## Success Criteria

- The reasoning panel can call Execute -> Verify -> Promote in sequence.
- Action payloads include case, draft, plan, request, child-pack, and pack-item identifiers.
- The UI displays planned, executed, verified, promoted, citable, and not-citable states.
- Detached backend tests pass.
- Detached frontend lint, tests, build, and dependency audit pass.
- No V1 changes, raw data upload, database migration, or raw data staging.
