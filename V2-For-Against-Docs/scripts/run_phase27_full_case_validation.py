#!/usr/bin/env python3
"""Run Phase 27 full 10-case offline validation for lawyer-review readiness."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from scripts.run_phase17_lawyer_review_pack_validation import (  # noqa: E402
    deterministic_reasoning_pack,
    pack_from_case,
)
from sl_legal_rag.strategy import validate_strategy_response_against_pack  # noqa: E402


DEFAULT_REPORT_JSON = PROJECT_ROOT / "data" / "tracking" / "phase27_full_10_case_validation" / "two_stage_search_report.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tracking" / "phase27_full_10_case_validation"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--top-documents", type=int, default=25)
    parser.add_argument("--chunk-chars", type=int, default=4000)
    parser.add_argument("--min-case-count", type=int, default=10)
    parser.add_argument("--min-promotion-eligible-items", type=int, default=1)
    parser.add_argument("--min-missing-evidence", type=int, default=5)
    parser.add_argument("--write-drafts", action="store_true")
    args = parser.parse_args(argv)
    if args.top_documents < 1:
        parser.error("--top-documents must be >= 1")
    if args.chunk_chars < 500:
        parser.error("--chunk-chars must be >= 500")
    if args.min_case_count < 1:
        parser.error("--min-case-count must be >= 1")
    return args


def resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path} must contain a non-empty cases array")
    return report


def promotion_readiness_items(pack: Any) -> list[dict[str, Any]]:
    ready: list[dict[str, Any]] = []
    for item in pack.items:
        citation = str(item.citation or "").strip()
        text = str(item.text or "").strip()
        document_type = str(item.document_type or "").lower()
        official_gazette = "gazette" in document_type
        if (item.authority_level <= 3 or official_gazette) and citation and text:
            ready.append(
                {
                    "pack_item_id": item.pack_item_id,
                    "document_id": item.document_id,
                    "title": item.title,
                    "document_type": item.document_type,
                    "authority_level": item.authority_level,
                    "citation": citation,
                    "anchor_status": "offline_text_present",
                    "promotion_basis": "phase27_offline_verification_readiness",
                }
            )
    return ready


def validate_case(case: dict[str, Any], args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "unknown_case")
    pack = pack_from_case(case, top_documents=args.top_documents, chunk_chars=args.chunk_chars)
    draft = deterministic_reasoning_pack(
        case,
        pack,
        provider_error="Phase 27 offline deterministic validation run; no LLM or database writes.",
    )
    validation_errors = validate_strategy_response_against_pack(draft, pack, requested_output="lawyer_review_pack")
    reasoning = draft.reasoning_pack
    promotion_items = promotion_readiness_items(pack)
    for_against_count = len(reasoning.for_against_brief) if reasoning else 0
    adverse_argument_count = (
        sum(1 for item in reasoning.for_against_brief if item.opposing_argument.strip())
        if reasoning
        else 0
    )
    missing_evidence_count = len(reasoning.missing_evidence_checklist) if reasoning else 0
    failures: list[str] = []
    if case.get("status") != "pass":
        failures.append("retrieval case did not pass")
    if validation_errors:
        failures.append("strategy validation errors present")
    if not draft.citation_validation.get("valid"):
        failures.append("citation validation failed")
    if for_against_count < 1 or adverse_argument_count < 1:
        failures.append("for/against reasoning is incomplete")
    if missing_evidence_count < args.min_missing_evidence:
        failures.append("missing evidence checklist is too small")
    if len(promotion_items) < args.min_promotion_eligible_items:
        failures.append("no promotion-eligible authority items found")

    if args.write_drafts:
        draft_dir = output_dir / "drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        (draft_dir / f"{case_id}.json").write_text(draft.model_dump_json(indent=2) + "\n", encoding="utf-8")

    return {
        "case_id": case_id,
        "retrieval_status": case.get("status"),
        "stage1_expected_recall": (case.get("metrics") or {}).get("stage1_expected_recall"),
        "top_k_expected_recall": (case.get("metrics") or {}).get("top_k_expected_recall"),
        "pack_item_count": len(pack.items),
        "claim_count": len(draft.claims),
        "for_against_count": for_against_count,
        "adverse_argument_count": adverse_argument_count,
        "missing_evidence_count": missing_evidence_count,
        "citation_validation_valid": bool(draft.citation_validation.get("valid")),
        "strategy_validation_errors": validation_errors,
        "promotion_eligible_item_count": len(promotion_items),
        "promotion_eligible_items": promotion_items[:12],
        "lawyer_review_ready": not failures,
        "failures": failures,
    }


def write_summary(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Phase 27 Full 10-Case Validation",
        "",
        f"- Status: `{report['status']}`",
        f"- Case count: `{report['case_count']}`",
        f"- Lawyer-review ready: `{report['lawyer_review_ready_count']}`",
        f"- Needs improvement: `{report['needs_improvement_count']}`",
        f"- Promotion-eligible authority items: `{report['promotion_eligible_item_total']}`",
        f"- Database writes: `none`",
        f"- Raw data upload: `none`",
        "",
        "## Cases",
        "",
    ]
    for case in report["cases"]:
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- Ready: `{case['lawyer_review_ready']}`",
                f"- Retrieval: `{case['retrieval_status']}`",
                f"- For/against arguments: `{case['for_against_count']}`",
                f"- Adverse arguments: `{case['adverse_argument_count']}`",
                f"- Missing evidence items: `{case['missing_evidence_count']}`",
                f"- Promotion-eligible items: `{case['promotion_eligible_item_count']}`",
                f"- Failures: `{'; '.join(case['failures']) if case['failures'] else 'none'}`",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report_path = resolve_project_path(args.report_json)
    output_dir = resolve_project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_report = load_report(report_path)
    cases = source_report["cases"]
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    case_reports = [validate_case(case, args, output_dir) for case in cases]
    ready_count = sum(1 for case in case_reports if case["lawyer_review_ready"])
    failures: list[str] = []
    if len(case_reports) < args.min_case_count:
        failures.append(f"case count below {args.min_case_count}")
    if any(not case["lawyer_review_ready"] for case in case_reports):
        failures.append("one or more cases need improvement")
    report = {
        "schema_version": "phase27_full_case_validation.v1",
        "status": "pass" if not failures else "needs_improvement",
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_report_json": str(report_path),
        "case_count": len(case_reports),
        "lawyer_review_ready_count": ready_count,
        "needs_improvement_count": len(case_reports) - ready_count,
        "promotion_eligible_item_total": sum(case["promotion_eligible_item_count"] for case in case_reports),
        "database_writes": "none",
        "raw_data_upload": "none",
        "failures": failures,
        "cases": case_reports,
    }
    report_out = output_dir / "phase27_full_validation_report.json"
    summary_out = output_dir / "phase27_full_validation_summary.md"
    report_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_summary(report, summary_out)
    print(
        json.dumps(
            {
                "status": report["status"],
                "case_count": report["case_count"],
                "lawyer_review_ready_count": report["lawyer_review_ready_count"],
                "needs_improvement_count": report["needs_improvement_count"],
                "report_path": str(report_out),
                "summary_path": str(summary_out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
