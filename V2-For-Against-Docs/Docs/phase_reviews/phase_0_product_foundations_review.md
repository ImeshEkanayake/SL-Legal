# Phase 0 Product Foundations Review

**Phase:** 0 - Product foundations  
**Status:** Repo-owned implementation complete; external legal signoff required before production approval.  
**Date:** 2026-05-24

## Scope

Phase 0 makes the product safety rules enforceable before downstream legal
reasoning, retrieval, drafting, and review workflows depend on them.

## Implemented Controls

- Product policy module: `rag/sl_legal_rag/product_policy.py`
- Prohibited-output detection:
  - final legal advice presented as definitive
  - guaranteed legal outcomes
  - fabricated citations, cases, documents, or evidence
  - concealed adverse authority
  - tampered or backdated records
  - bypassed lawyer review
- Legal risk levels:
  - low
  - medium
  - high
  - critical
- Review requirements:
  - high and critical legal work require qualified lawyer review
  - medium legal research requires lawyer or supervised legal reviewer review
- Source reliability tiers:
  - official
  - court or tribunal
  - licensed publisher
  - secondary
  - unverified
- Authority hierarchy labels for pack/source inspection.
- Strategy generation now runs product-policy validation after pack-boundary
  citation validation.

## Test Evidence

Focused Phase 0 tests:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport pytest tests/test_product_policy.py tests/test_llm_agent_boundaries.py -q
```

Result:

```text
12 passed
```

Full regression suite should pass before moving to the next phase.

## Review Findings

No repo-owned blocker remains for Phase 0 enforcement.

The policy layer is deterministic and auditable, but it is not a substitute for
legal review. It blocks known unacceptable patterns and forces lawyer-review
posture for legal work; it does not claim to understand every possible unsafe
instruction.

## Required External Signoffs

These cannot be completed by code alone:

- Legal review of prohibited-use categories and wording.
- Legal review of Sri Lankan authority hierarchy labels.
- Product/legal review of what counts as low, medium, high, and critical risk.
- Security/privacy review when these policies are exposed through production UI
  and audit exports.

## Gate Decision

Engineering gate: passed for Phase 0 implementation.  
Production approval gate: pending external legal signoff.
