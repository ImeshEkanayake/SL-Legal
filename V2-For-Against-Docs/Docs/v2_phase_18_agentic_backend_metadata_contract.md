# V2 Phase 18 Agentic Backend Metadata Contract

## Scope

Phase 18 connects the Phase 16 agentic research contracts to the existing backend strategy-draft workflow. It records tool routing, matter memory, clarification needs, and authority candidates in existing JSON metadata fields.

No database migration is applied. No V1 files, raw data, generated logs, environment files, or release bundles are committed.

## Backend Flow

The `/v1/strategy/draft` workflow now performs these steps:

1. Load the authorized sealed research pack.
2. Generate and validate the pack-bounded strategy or reasoning-pack draft.
3. Build an `AgentResearchPlan` and `MatterMemory` using the deterministic `agentic_research` service.
4. Persist `agentic_research_plan` and `matter_memory` in `drafts.metadata`.
5. Persist the same metadata in the assistant chat message when a thread is present.
6. Write the same structures into the completed `agent_runs.output` payload.

## Metadata Shape

Draft and chat-message metadata may include:

```json
{
  "agentic_research_plan": {
    "schema_version": "agent_research_plan.v1"
  },
  "matter_memory": {
    "schema_version": "matter_memory.v1"
  }
}
```

These fields are additive. Existing `reasoning_pack`, `citation_validation`, `missing_authorities`, `warnings`, `counterarguments`, `risk_rankings`, and `next_retrieval_questions` remain unchanged.

## Service Boundary

`rag/sl_legal_rag/agentic_research.py` is deterministic and does not:

- call an LLM;
- query the database;
- browse official sources;
- mutate the database;
- promote authority candidates;
- produce final legal advice.

It only wraps already-loaded pack and draft objects with auditable workflow metadata.

## Authority Boundary

Missing authorities and authority-related missing-evidence tasks become `AuthorityExpansionCandidate` records. They remain non-citable until a future phase retrieves, anchors, verifies, reviews, and seals them into a research pack.

## Clarification Boundary

Clarification needs are recorded but do not block persistence. They must remain visible to lawyers and later workflow stages. A stronger preliminary opinion should not be generated when blocking clarification needs remain unresolved.

## Validation Requirements

Phase 18 validation must cover:

- deterministic bundle creation;
- DB-first tool route metadata;
- authority candidates remain non-citable;
- clarification policy for weak inputs;
- `/v1/strategy/draft` passes agentic metadata into persistence;
- draft detail returns `metadata.agentic_research_plan` and `metadata.matter_memory`;
- existing reasoning-pack persistence remains unchanged.
