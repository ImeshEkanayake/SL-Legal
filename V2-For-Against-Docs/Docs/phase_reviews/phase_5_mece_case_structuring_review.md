# Phase 5 MECE Case Structuring Review

**Phase:** 5 - MECE case structuring  
**Status:** Repo-owned implementation complete; lawyer review of sample decompositions required before production approval.  
**Date:** 2026-05-24

## Scope

Phase 5 structures user-provided case facts without answering law. The output
must preserve raw-input provenance, source spans, uncertainty labels, missing
information, ambiguities, contradictions, and retrieval-only query plans.

## Implemented Controls

- MECE prompt contract forbids legal answers and authority citation.
- Raw input SHA-256 is computed by the backend and forced onto model output.
- Source-span validator:
  - requires exact quotes
  - repairs incorrect offsets when the quote is found
  - warns on missing or invalid spans
- Completeness validator:
  - duplicate fact ID detection
  - unknown issue-supporting fact ID detection
  - inferred issue reason requirement
  - non-empty input must produce non-missing facts
  - source-span coverage warning for longer narratives
  - facts/issues require retrieval queries
- Endpoint audit records keep counts and raw-input hash, not raw facts.

## Test Evidence

Focused tests:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport pytest tests/test_llm_agent_boundaries.py tests/test_api_research_pack_endpoint.py -q
```

Required final check:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport python scripts/run_quality_checks.py
```

## Review Findings

No repo-owned blocker remains for Phase 5 MECE structuring safeguards.

Production approval still requires a lawyer/domain review of sample
decompositions across real case narratives and an expanded golden set for
contradictions, ambiguity, and no-fact-loss behavior.

## Required External Signoffs

- Lawyer review of sample decompositions.
- Product review of issue taxonomy and certainty labels.
- Evaluation review for no-fact-loss golden narratives.

## Gate Decision

Engineering gate: passed for Phase 5 case structuring safeguards.  
Production approval gate: pending lawyer/domain sample review.
