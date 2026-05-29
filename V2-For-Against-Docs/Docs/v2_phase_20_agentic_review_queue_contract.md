# V2 Phase 20 Agentic Review Queue Contract

## Scope

Phase 20 makes agentic workflow metadata actionable through the existing lawyer review queue. It adds review tasks for clarification blockers and authority candidates without applying a database migration.

No V1 files, raw data, environment files, generated logs, release bundles, or database schema are changed.

## Review Item Types

Phase 20 adds two draft-scoped review item types:

- `clarification_need`
- `authority_candidate`

These item types use the existing `review_items` table and point to the strategy draft ID. The underlying clarification and candidate details remain in `drafts.metadata.agentic_research_plan` and `drafts.metadata.matter_memory`.

## Creation Rules

When `persist_strategy_draft` receives `matter_memory`:

- create one high-priority `clarification_need` review item when unresolved blocking clarifications exist;
- create one high-priority `authority_candidate` review item when authority candidates exist;
- keep existing `draft`, `legal_claim`, `adverse_evidence`, and `missing_evidence` review items unchanged.

## Decision Rules

The existing review decision endpoint can approve, reject, or request changes on the new review item types.

Decisions:

- update the `review_items` row;
- write an audit event;
- do not mutate the draft status;
- do not promote candidate authorities;
- do not mark clarifications as answered.

Promotion and clarification-answer workflows remain separate future phases.

## Display Rules

Review queue titles are:

- `Clarification review`
- `Authority candidate review`

The review workspace can display and decide these items through the existing generic review UI.

## Validation Requirements

Phase 20 validation must cover:

- review item creation for blocking clarification needs;
- review item creation for authority candidates;
- workspace snapshot includes the new review item types;
- review list titles are non-empty and specific;
- review decisions are accepted and audited for the new types;
- existing draft, claim, adverse, and missing-evidence review behavior remains unchanged.
