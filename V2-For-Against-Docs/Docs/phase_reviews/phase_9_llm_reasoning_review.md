# Phase 9 Review Packet: LLM Reasoning

## Scope

Phase 9 hardens the reasoning layer that consumes Legal Research Packs. The LLM
may draft strategy material, but the backend now enforces pack-bounded output
contracts before the result can be returned or persisted.

## Implementation Evidence

- `rag/sl_legal_rag/models.py`
  - extended `StrategyDraftResponse` with counterarguments, risk rankings,
    next-retrieval questions, and citation-validation metadata;
  - added structured counterargument and risk-ranking models;
  - added `all_pack_item_ids()` so validation covers every cited pack item.
- `rag/sl_legal_rag/strategy.py`
  - prompt requires claims, counterarguments, risk ranking, missing authorities,
    and next-retrieval questions;
  - deterministic citation extraction supports full prefixed pack item IDs;
  - validator rejects unknown answer citations, unknown counterargument and risk
    citations, pack ID mismatch, and uncited legal claim sentences;
  - generation blocks prompt-injection attempts before model output is accepted;
  - returned drafts include deterministic citation-validation summaries.
- `rag/sl_legal_rag/product_policy.py`
  - blocks attempts to override pack-boundary rules or force hidden-source use.
- `rag/sl_legal_rag/db/repositories.py`
  - persists counterargument, risk, next-retrieval, and citation-validation
    metadata with chat messages and drafts;
  - checks every cited pack item across the whole strategy response before
    saving.
- `rag/sl_legal_rag/api.py`
  - `/v1/strategy/validate` now checks answer text, claims, counterarguments,
    and risk rankings against the stored pack items.

## Test Evidence

- `tests/test_strategy_reasoning.py`
  - structured pack-bounded reasoning is accepted;
  - full prefixed citations are extracted;
  - uncited legal sentences are rejected;
  - fabricated full-prefix citations are rejected;
  - out-of-pack counterargument and risk citations are rejected;
  - prompt-injection input is blocked before generation;
  - citation-validation summaries report unknown citations.
- Existing API, DB, and policy tests verify persistence and endpoint behavior.

## Review Notes

- Strategy output remains a lawyer-review draft, never final advice.
- Counterarguments and risk rankings can only cite pack items already present in
  the sealed pack.
- Missing-source and source-reliability warnings are carried into the returned
  draft warnings so lawyer review sees retrieval limits.
- Next-retrieval questions are structured and can feed the expansion endpoint
  from Phase 8.

## Residual Production Gates

- Qualified lawyer review of generated strategy samples from real packs.
- Prompt and safety review for the exact JSON prompt.
- Golden-pack regression set for known legal scenarios and adverse-authority
  coverage.
