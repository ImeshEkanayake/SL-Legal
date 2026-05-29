# V2 Phase 27 Contract: Full 10-Case Verification and Promotion Validation

## Purpose

Phase 27 validates the V2 for/against reasoning workflow across the full tuned 10-case set after authority verification and controlled promotion have been implemented.

## Inputs

- `rag/evals/two_stage_tuned_cases.json`
- Local read-only corpus/search database
- Existing Phase 17 lawyer-review pack construction and deterministic fallback logic

## Validation Flow

1. Run the 10-case two-stage retrieval evaluator.
2. Build 25-document validation packs per case.
3. Generate offline lawyer-review packs without database writes.
4. Confirm for/against reasoning is present.
5. Confirm missing-evidence checklists are substantive.
6. Score authority promotion readiness from citable primary/legal authority items.
7. Write aggregate JSON and Markdown reports under `data/tracking/phase27_full_10_case_validation`.

## Authority Readiness Rules

Promotion-readiness counts:

- Acts, statutes, and regulations;
- Supreme Court, Court of Appeal, and law-report material;
- official Gazettes, including Extraordinary Gazettes.

Promotion-readiness does not itself promote anything. Production promotion still requires the Phase 25 and Phase 26 API flow.

## Success Criteria

- All 10 tuned cases complete without runtime errors.
- Retrieval reports `10/10` cases passing.
- Lawyer-review readiness reports `10/10` cases ready.
- Each case has for/against reasoning, adverse reasoning, missing evidence, and at least one promotion-eligible authority item.
- No database writes, raw data upload, V1 changes, or schema migration.

## Outputs

Generated outputs are local tracking artifacts and are not committed to normal Git:

- `data/tracking/phase27_full_10_case_validation/two_stage_search_report.json`
- `data/tracking/phase27_full_10_case_validation/two_stage_search_summary.md`
- `data/tracking/phase27_full_10_case_validation/phase27_full_validation_report.json`
- `data/tracking/phase27_full_10_case_validation/phase27_full_validation_summary.md`
