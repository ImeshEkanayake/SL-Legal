# V2 Phase 17 Release: Lawyer Review Pack Validation

## Release Goal

Phase 17 validates the missing reasoning step after Phase 16 retrieval validation. It turns the union bargaining retrieval report into a bounded `LegalResearchPack`, generates a `lawyer_review_pack`, and surfaces the actual for/against arguments, missing evidence checklist, preliminary opinion, and lawyer-review questions.

## Included

- `scripts/run_phase17_lawyer_review_pack_validation.py`: builds a validation research pack from the Phase 16 report, calls `requested_output="lawyer_review_pack"`, and writes ignored local validation artifacts.
- `rag/sl_legal_rag/strategy.py`: adds one validation-repair retry when model output fails pack-boundary checks.
- `tests/test_strategy_reasoning.py`: covers the repair retry for uncited legal-claim sentences.

## Validation Results

Local validation completed on 2026-05-29:

- Phase 17 lawyer-review pack runner:
  - Log: `logs/test-runs/phase17-lawyer-review-pack-25docs-longtext-normalized-20260529T071343Z.log`
  - Result: `pass`.
  - Pack items: `25`.
  - Extracted text: `4,000` characters per pack item.
  - Pack token estimate: `24,992`.
  - Claims: `6`.
  - For/against arguments: `4`.
  - Missing evidence entries: `11`.
  - Citation validation: `valid`, `0` issues.
  - Authority identifiers: generated from source type and legal identifier, for example `Extraordinary Gazette No. 1862/08 (2014)`, not page numbers.
- Focused reasoning tests:
  - Command: `PYTHONPATH=rag uv run --with pytest --with pydantic --with pydantic-settings --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 --with eval-type-backport python -m pytest tests/test_azure_openai_config.py tests/test_reasoning_pack_models.py tests/test_strategy_reasoning.py -q`
  - Result: `20 passed`.

## Output Artifacts

Generated outputs are local-only and intentionally ignored by Git:

- `data/tracking/phase17_lawyer_review_pack_validation/phase17_research_pack.json`
- `data/tracking/phase17_lawyer_review_pack_validation/phase17_lawyer_review_pack.json`
- `data/tracking/phase17_lawyer_review_pack_validation/phase17_lawyer_review_pack_summary.md`
- `data/tracking/phase17_lawyer_review_pack_validation/phase17_validation_report.json`
- Corrected four-document validation artifacts are written under:
  - `data/tracking/phase17_lawyer_review_pack_validation_4docs/phase17_research_pack.json`
  - `data/tracking/phase17_lawyer_review_pack_validation_4docs/phase17_lawyer_review_pack.json`
  - `data/tracking/phase17_lawyer_review_pack_validation_4docs/phase17_lawyer_review_pack_summary.md`
  - `data/tracking/phase17_lawyer_review_pack_validation_4docs/phase17_validation_report.json`
- Final 25-document long-text validation artifacts are written under:
  - `data/tracking/phase17_lawyer_review_pack_validation_25docs_longtext/phase17_research_pack.json`
  - `data/tracking/phase17_lawyer_review_pack_validation_25docs_longtext/phase17_lawyer_review_pack.json`
  - `data/tracking/phase17_lawyer_review_pack_validation_25docs_longtext/phase17_lawyer_review_pack_summary.md`
  - `data/tracking/phase17_lawyer_review_pack_validation_25docs_longtext/phase17_validation_report.json`

## Boundary Notes

- No V1 changes.
- No raw data upload.
- No database migration.
- No persisted case, draft, claim, or review-item rows were created by the Phase 17 validation runner.
- The generated legal reasoning remains preliminary and requires qualified Sri Lankan lawyer review before reliance.

## Next Phase

The next phase should run backend persistence validation for a controlled test matter so `drafts.metadata.reasoning_pack`, draft content, and review queue items can be verified end to end.
