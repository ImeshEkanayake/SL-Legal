# V2 Phase 19 Agentic Workspace Contract

## Scope

Phase 19 exposes the Phase 18 agentic research metadata in the lawyer workspace. The UI shows tool routing, matter memory, clarification needs, authority candidates, and sealed-pack boundaries beside the existing reasoning pack.

No V1 files, raw data, generated logs, environment files, release bundles, or database schema are changed.

## Backend Snapshot Contract

Workspace draft summaries may include:

- `reasoningPack`
- `agenticResearchPlan`
- `matterMemory`

`agenticResearchPlan` and `matterMemory` are read from existing `drafts.metadata` fields and returned through the existing workspace snapshot endpoint.

## Frontend Contract

The Reasoning workspace renders an `Agentic workflow` section when either `agenticResearchPlan` or `matterMemory` is present.

The section must show:

- reviewer summary;
- tool route with tool name, source boundary, status, purpose, reviewer note, and result count;
- clarification needs, including whether they block stronger preliminary opinion;
- authority candidates and their non-citable status;
- sealed pack count;
- adverse material count;
- missing-evidence task count;
- matter memory client position, facts, adverse material, and missing tasks;
- promoted pack-item buttons only when a candidate has been promoted.

## Safety Rules

- Candidate authorities must be visually separate from sealed-pack citations.
- Candidate authorities must not appear as active pack-item buttons unless `promoted_pack_item_ids` exist.
- Clarification blockers must be visible before the preliminary opinion.
- Tool traces must show source boundary so reviewers can distinguish user input, database retrieval, candidates, official-source planning, sealed-pack drafting, and generated review output.
- No UI copy should describe candidates as verified legal authority unless their status is promoted and verified by a later workflow.

## Validation Requirements

Phase 19 validation must cover:

- workspace snapshot returns `agenticResearchPlan` and `matterMemory`;
- TypeScript workspace types include agentic metadata;
- Reasoning UI renders the agentic workflow panel;
- UI renders tool route, clarification blockers, candidate authorities, and matter memory;
- existing reasoning pack UI remains visible;
- frontend lint and component tests pass.
