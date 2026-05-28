# V2 Phase 4 Reasoning Pack Contract

## Scope

Phase 4 adopts the hybrid workstream from `/Users/imeshekanayake/Downloads/detailed.md` for production lawyer-review reasoning.

Workflow:

```text
Retrieval Pack -> Authority Verification -> Issue Matrix -> Legal Element Matrix -> Fact-to-Law Mapping -> For/Against Brief -> Missing Evidence Checklist -> Preliminary Legal Opinion -> Lawyer Review Pack
```

This phase does not change V1, does not upload raw data, and does not apply a database migration. Structured reasoning output is stored in existing draft metadata until a reviewed schema migration is approved.

## Backend Contract

`rag/sl_legal_rag/models.py` defines the Phase 4 structured output:

- `AuthorityVerification`
- `IssueMatrixItem`
- `LegalElement`
- `FactLawMapping`
- `ForAgainstArgument`
- `PreliminaryLegalOpinion`
- `LawyerReviewPack`
- `ReasoningPackOutput`

`StrategyDraftResponse.reasoning_pack` carries the structured pack. `PersistedStrategyDraftResponse.reasoning_review_item_ids` reports additional review queue entries created for adverse reasoning and missing evidence.

## Strategy Outputs

`rag/sl_legal_rag/strategy.py` supports these `requested_output` values:

- `for_against_brief`
- `preliminary_legal_opinion`
- `lawyer_review_pack`

For those output types, the JSON response must include `reasoning_pack`. The human-readable answer is still stored in `drafts.content_markdown`.

## Persistence

`rag/sl_legal_rag/db/repositories.py` stores:

- human-readable output in `drafts.content_markdown`
- structured output in `drafts.metadata.reasoning_pack`
- request type in `drafts.metadata.requested_output`
- chat-agent metadata in the assistant message metadata when a thread is available
- normal draft and claim review items
- Phase 4 review items with `item_type` values:
  - `adverse_evidence`
  - `missing_evidence`

The existing review workflow can approve, reject, or request changes for those Phase 4 review items without changing draft status.

## Validation Rules

Phase 4 validation enforces:

- pack-bounded citations only
- rejection of reasoning-pack pack item IDs outside the sealed research pack
- rejection of uncited legal claim sentences in the answer
- rejection of outcome-guarantee wording
- lawyer verification required for reasoning packs and preliminary opinions
- verified authority entries require official source and amendment checks
- verified fact-to-law mappings require pack citations
- missing evidence checklist is required
- issue references in fact-to-law mappings and for/against arguments must match the issue matrix
- for/against brief must include opposing analysis

Unverified legal propositions must remain marked for lawyer review.

## Tests

Phase 4 adds or extends tests for:

- schema acceptance and validator rejection cases
- cautious preliminary opinion wording
- authority verification checks
- citation checks for reasoning-pack references
- generated reasoning-pack validation
- draft persistence of structured metadata
- review queue entries for draft, claim, adverse reasoning, and missing evidence

## Release Boundary

Out of scope for Phase 4:

- raw data upload
- database migration execution
- V1 changes
- production UI implementation
- automated legal conclusion approval
