# V2 Phase 16 Agentic Research Workflow Contract

## Scope

Phase 16 adds the foundation contracts for a tool-routed legal research workflow. It does not run autonomous research by itself; it defines the auditable structures that future services must use when planning, retrieving, expanding authorities, checking official sources, asking clarifying questions, drafting from sealed packs, and producing lawyer-review packs.

No V1 files, raw corpus data, generated logs, release bundles, environment files, or database schema are changed.

## Tool Router Contract

Every routed research step must be represented as an `AgentToolTrace` with:

- `tool_name`
- `purpose`
- `source_boundary`
- `input_summary`
- `result_count` or a non-completed status
- `status`
- `selected_outputs`
- `reviewer_note`
- optional metadata, including `metadata.error` when failed

Supported tools:

- `case_intake_structurer`
- `search_database`
- `expand_authorities`
- `official_source_check`
- `ask_clarification`
- `answer_from_pack`
- `lawyer_review_pack`

## Source Boundaries

Tools may only operate inside their approved source boundary:

- `case_intake_structurer`: `user_input`
- `search_database`: `database`
- `expand_authorities`: `candidate_authorities` or `database`
- `official_source_check`: `official_source`
- `ask_clarification`: `user_input`
- `answer_from_pack`: `sealed_pack`
- `lawyer_review_pack`: `sealed_pack` or `generated_draft`

This keeps wider search, official-source checks, sealed-pack reasoning, and generated drafting visibly separate.

## Authority Candidate Boundary

Wider authority expansion creates `AuthorityExpansionCandidate` records. A candidate is not citable unless:

- its status is `promoted_to_sealed_pack`; and
- it carries one or more `promoted_pack_item_ids`.

Candidate metadata verification is not the same as verified legal authority. Until a candidate is retrieved, anchored, reviewed, and sealed into a pack, it must remain marked for lawyer verification.

## Clarification Policy

`ClarificationNeed` records are required when a material missing item affects the strength or direction of the preliminary opinion. Covered categories include:

- client position
- parties
- jurisdiction
- dates
- relief sought
- registration number
- case number
- procedural posture
- material fact

If a plan contains clarification needs, it must include an `ask_clarification` trace.

## Matter Memory

`MatterMemory` records the current research state without a database migration. It can hold:

- client position
- selected authorities
- sealed pack IDs
- candidate authorities
- client facts
- adverse material
- missing-evidence tasks
- clarification needs
- tool traces
- review state

Promoted authority candidates require at least one sealed pack ID in matter memory.

## Plan Sequencing Rules

`AgentResearchPlan` enforces the first safe sequencing rules:

- `answer_from_pack` requires a prior `search_database` trace.
- `official_source_check` requires a prior `expand_authorities` trace.
- clarification needs require an `ask_clarification` trace.
- authority candidates must reference a known tool trace.

## Testing Rules

Phase 16 unit tests must cover:

- DB-first tool route acceptance.
- invalid source-boundary rejection.
- completed trace result-count requirements.
- failed trace error metadata requirements.
- official-source check sequencing.
- clarification trace requirements.
- authority candidate promotion boundaries.
- matter-memory candidate trace references and sealed-pack requirements.
