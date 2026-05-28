# V2 Phase 5 Production UI Contract

## Scope

Phase 5 makes the Phase 4 reasoning pack usable inside the V2 case workspace. Lawyers can inspect the issue matrix, preliminary opinion, fact-to-law mapping, for/against analysis, missing evidence, authority verification, source pack citations, and review queue decisions without leaving the workspace.

No V1 files, raw corpus data, or database schema are changed.

## Workspace Contract

`CaseWorkspaceSnapshot.drafts[]` now includes:

- `requestedOutput`
- `reasoningPack`

The reasoning pack is read from existing `drafts.metadata.reasoning_pack`, preserving the Phase 4 no-migration boundary.

## UI Views

The workspace adds a reasoning-first view:

- right rail navigation item: `Reasoning`
- main workspace title: `Reasoning Pack`
- draft selector for available reasoning drafts
- preliminary opinion panel
- issue matrix
- for/against arguments
- fact-to-law mappings
- missing evidence checklist
- authority verification status
- source pack item buttons that jump to the research pack evidence view

The review view now records decisions through the existing signed backend review endpoint:

- approve
- request changes
- reject

Negative decisions require a comment through the backend contract.

## Safety Rules

- Reasoning UI displays only structured pack output already persisted by Phase 4 validation.
- Citation buttons use existing `pack_item_id` values and open the research pack evidence view.
- Review decisions continue through the audited backend review workflow.
- The UI does not present automated approval or legal-advice finality.

## Tests

Phase 5 coverage includes:

- workspace rendering with reasoning-pack data
- right rail navigation to the reasoning view
- preliminary opinion visibility
- issue matrix and for/against visibility
- source pack citation navigation from reasoning sections
- review decision action wiring
- backend workspace snapshot reasoning-pack metadata
- existing document, pack, chat, and review workspace coverage

## Release Boundary

Out of scope for Phase 5:

- data upload
- database migration
- new LLM reasoning behavior
- V1 changes
- load-test implementation beyond existing release gates
