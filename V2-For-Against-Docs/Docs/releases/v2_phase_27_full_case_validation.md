# V2 Phase 27 Release: Full 10-Case Verification and Promotion Validation

## Release Goal

Phase 27 validates the V2 workflow across the full tuned 10-case set after authority verification and controlled promotion are available.

## Included

- `scripts/run_phase27_full_case_validation.py`: aggregate 10-case lawyer-review and promotion-readiness validator.
- `rag/sl_legal_rag/db/repositories.py`: official Gazette verification boundary fix.
- `tests/test_phase17_validation_runner.py`: Phase 27 runner and promotion-readiness coverage.
- `tests/test_agentic_research_models.py`: official Gazette promotion validation.
- `Docs/v2_phase_27_full_case_validation_contract.md`: validation contract.
- `Docs/v2_production_product_roadmap.md`: Phase 27 roadmap entry.
- `Docs/v2_codebase_map.md`: Phase 27 code map entry.

## Validation Results

Local targeted validation completed on 2026-05-30:

- Python compile check:
  - Command: `python3 -m py_compile scripts/run_phase27_full_case_validation.py rag/sl_legal_rag/db/repositories.py`
  - Result: passed.
- Phase 27 focused tests:
  - Command: `PYTHONPATH=rag:. uv run --with pytest --with pydantic --with pydantic-settings --with eval-type-backport --with sqlalchemy --with 'psycopg[binary]' --with fastapi --with httpx --with pypdfium2 python -m pytest tests/test_agentic_research_models.py tests/test_phase17_validation_runner.py -q`
  - Result: `22 passed`.
- Full 10-case retrieval validation:
  - Command: `PYTHONPATH=rag uv run --with psycopg[binary] --with pydantic --with eval-type-backport python scripts/run_two_stage_recall_precision_checks.py --fixture rag/evals/two_stage_tuned_cases.json --output-dir data/tracking/phase27_full_10_case_validation --top-k 25 --stage1-limit 750 --title-expansion-limit 1500`
  - Result: `10/10` cases passed; stage-1 expected recall `1.0` and top-25 expected recall `1.0` for every case.
- Phase 27 aggregate validation:
  - Command: `PYTHONPATH=rag:. uv run --with pydantic --with pydantic-settings --with eval-type-backport python scripts/run_phase27_full_case_validation.py --report-json data/tracking/phase27_full_10_case_validation/two_stage_search_report.json --output-dir data/tracking/phase27_full_10_case_validation --top-documents 25 --chunk-chars 4000`
  - Result: `pass`; `10/10` lawyer-review ready cases; `235` promotion-eligible authority items.
- Secret scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python scripts/check_no_plaintext_secrets.py`
  - Result: passed.
- Marker scan:
  - Command: `PYTHONPATH=rag uv run --with pydantic --with eval-type-backport python -c 'import scripts.run_quality_checks as q; q.assert_no_unfinished_markers(); print("marker scan passed")'`
  - Result: passed.

Detached validation completed on 2026-05-30:

- Backend test suite:
  - Command: `scripts/run_detached_quality_gate.sh tests phase27-full-case-validation-tests`
  - Log: `logs/test-runs/phase27-full-case-validation-tests.log`
  - Result: `317 passed`; exit status `0`.
- Frontend quality gate:
  - Command: `scripts/run_detached_quality_gate.sh frontend phase27-full-case-validation-frontend`
  - Log: `logs/test-runs/phase27-full-case-validation-frontend.log`
  - Result: ESLint passed, Vitest `16 passed`, Next production build passed, `npm audit --audit-level=moderate` found `0 vulnerabilities`; exit status `0`.

## Case Summary

- `industrial_disputes_union_bargaining`: ready, 25 promotion-eligible authority items.
- `fundamental_rights_arrest_detention`: ready, 25 promotion-eligible authority items.
- `land_acquisition_compensation`: ready, 25 promotion-eligible authority items.
- `inland_revenue_tax_assessment`: ready, 25 promotion-eligible authority items.
- `local_authority_trade_licence_nuisance`: ready, 25 promotion-eligible authority items.
- `companies_minority_shareholder_oppression`: ready, 25 promotion-eligible authority items.
- `criminal_assault_evidence_procedure`: ready, 15 promotion-eligible authority items.
- `customs_import_duty_forfeiture`: ready, 25 promotion-eligible authority items.
- `immigration_visa_overstay_removal`: ready, 23 promotion-eligible authority items.
- `intellectual_property_trademark_infringement`: ready, 22 promotion-eligible authority items.

## Safety Boundary

- No V1 changes.
- No raw data upload.
- No database migration.
- No database writes from the validation runner.
- Generated `data/tracking` reports remain local and are not committed to normal Git.

## Next Phase

The next step should run UI E2E against a representative case using the verified/promoted authority path, then capture screenshots and API evidence for lawyer workflow readiness.
