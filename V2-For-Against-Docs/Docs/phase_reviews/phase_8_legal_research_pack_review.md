# Phase 8 Review Packet: Legal Research Pack

## Scope

Phase 8 seals Legal Research Packs as auditable, immutable evidence bundles for
downstream LLM reasoning. The implementation adds canonical pack hashes, token
counts, source warnings, per-item scoring details, retrieval traces, version
lineage, and a signed expansion endpoint.

## Implementation Evidence

- `rag/sl_legal_rag/research_pack.py`
  - canonical pack payload and hash generation;
  - pack sealing with schema version, token count, source warnings, and trace;
  - contract validation for item IDs, citations, selected text, token budget,
    and trace evidence;
  - helper for expansion query requests.
- `rag/sql/010_research_pack_contract.sql`
  - `research_packs` columns for schema version, parent pack, version, token
    count, source warnings, and retrieval trace;
  - `research_pack_items` columns for token estimate, scoring details, and item
    trace;
  - `retrieval_events` columns for trace, parent pack, and version.
- `rag/sl_legal_rag/db/repositories.py`
  - persists only sealed packs;
  - rejects same `pack_id` with different canonical content;
  - links repeated saves to cases without mutating the saved pack;
  - exposes child-version calculation for expansion.
- `rag/sl_legal_rag/api.py`
  - `POST /v1/research/packs` persists sealed packs;
  - `POST /v1/research/packs/{pack_id}/expand` verifies parent-pack access,
    creates a child pack, increments version lineage, and audits the action.

## Test Evidence

- `tests/test_research_pack_contract.py`
  - sealing adds hash, trace, token count, item scoring, and warnings;
  - contract validation catches non-canonical item IDs and token overflow;
  - empty packs require a missing-source warning;
  - expansion request preserves parent filters and budget.
- `tests/test_api_research_pack_endpoint.py`
  - expansion endpoint links parent pack, case, version, audit data, and rate
    limit policy.
- `tests/test_db_access_layer.py`
  - repeated save with the same canonical pack is idempotent;
  - same `pack_id` with changed content raises an immutability violation.

## Review Notes

- LLM reasoning must consume only sealed pack fields and cited `pack_item_id`
  values.
- Pack expansion is append-only: parent content remains fixed, and child packs
  carry `parent_pack_id` plus an incremented `pack_version`.
- UX review should verify that the pack inspector displays source warnings,
  trace stages, token budget, parent lineage, and item scoring details.
- Legal review should confirm that source warnings are clear enough for lawyer
  review before any strategy or drafting output relies on the pack.

## Residual Production Gates

- Review pack inspector UX once the frontend is built.
- Run legal-domain sample review against real sealed packs.
- Add benchmark-backed thresholds for trace completeness and selected-source
  quality once the golden retrieval set is finalized.
