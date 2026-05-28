# Phase 3 Extraction and OCR Review

**Phase:** 3 - Extraction and OCR  
**Status:** Repo-owned quality-gate implementation complete; production extraction engine, load evidence, and manual QA signoff required before production approval.  
**Date:** 2026-05-24

## Scope

Phase 3 prevents extracted or OCR text from silently entering legal-answer
context when the text is empty, malformed, or too low confidence for legal
reliance.

## Implemented Controls

- Extraction quality module: `rag/sl_legal_rag/extraction_quality.py`
- OCR confidence bands:
  - high
  - medium
  - low
  - unusable
  - unknown
- Page-level quality decisions:
  - text length
  - alphanumeric ratio
  - OCR confidence
  - quality score
  - quality flags
  - legal-answer eligibility
  - manual-review requirement
- Document-level aggregation:
  - page count
  - eligible page count
  - blocked page count
  - average quality score
  - aggregate quality flags
- Product policy now warns when a research pack includes blocking extraction/OCR
  quality flags.

## Test Evidence

Focused tests:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport pytest tests/test_extraction_quality.py -q
```

Required final check:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
  --with pydantic-settings --with fastapi --with pytest --with httpx \
  --with eval-type-backport python scripts/run_quality_checks.py
```

## Review Findings

No repo-owned blocker remains for extraction/OCR quality classification.

The current implementation is the policy and scoring layer. Full production
approval still requires wiring every extraction/OCR worker to emit these quality
decisions, then running golden-PDF tests and throughput/load tests over the
actual corpus.

## Required External Signoffs

- Manual QA sample review by document category.
- OCR/load-performance review on the real corpus.
- Legal/domain review of low-confidence exclusion thresholds.
- Review of any layout-aware extraction engine selected for complex PDFs.

## Gate Decision

Engineering gate: passed for Phase 3 extraction/OCR quality controls.  
Production approval gate: pending worker integration, load evidence, and manual QA.
