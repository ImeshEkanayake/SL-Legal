#!/usr/bin/env python3
"""Evaluate V2 supportive and adverse retrieval fixture results separately."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.retrieval_eval import (  # noqa: E402
    RetrievalEvalCase,
    assert_blind_cases_include_adverse,
    evaluate_retrieval_cases,
)


DEFAULT_FIXTURE = PROJECT_ROOT / "rag" / "evals" / "v2_for_against_retrieval_fixture.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--k", type=int, default=20)
    parser.add_argument("--min-supportive-recall", type=float, default=0.90)
    parser.add_argument("--min-adverse-recall", type=float, default=0.90)
    parser.add_argument("--require-adverse", action="store_true", default=True)
    return parser.parse_args(argv)


def load_fixture(path: Path) -> list[RetrievalEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError(f"{path} must contain a non-empty cases array")
    cases = []
    for raw_case in raw_cases:
        cases.append(
            RetrievalEvalCase(
                query_id=str(raw_case["query_id"]),
                expected_chunk_ids=tuple(str(item) for item in raw_case["expected_chunk_ids"]),
                ranked_chunk_ids=tuple(str(item) for item in raw_case["ranked_chunk_ids"]),
                evidence_label=str(raw_case.get("evidence_label") or "supportive"),
            )
        )
    return cases


def evaluate_fixture(path: Path, *, k: int, require_adverse: bool) -> dict[str, Any]:
    cases = load_fixture(path)
    if require_adverse:
        assert_blind_cases_include_adverse(cases)
    result = evaluate_retrieval_cases(cases, k=k)
    return {
        "fixture_path": str(path),
        "case_count": result.case_count,
        "recall_at_k": result.recall_at_k,
        "mrr": result.mrr,
        "ndcg_at_k": result.ndcg_at_k,
        "missing_query_ids": list(result.missing_query_ids),
        "recall_by_label": result.recall_by_label or {},
        "case_count_by_label": result.case_count_by_label or {},
    }


def threshold_failures(report: dict[str, Any], *, min_supportive_recall: float, min_adverse_recall: float) -> list[str]:
    recall_by_label = dict(report["recall_by_label"])
    failures = []
    if float(recall_by_label.get("supportive", 0.0)) < min_supportive_recall:
        failures.append(f"supportive recall below {min_supportive_recall}")
    if float(recall_by_label.get("adverse", 0.0)) < min_adverse_recall:
        failures.append(f"adverse recall below {min_adverse_recall}")
    return failures


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    fixture_path = Path(args.fixture)
    if not fixture_path.is_absolute():
        fixture_path = PROJECT_ROOT / fixture_path
    report = evaluate_fixture(fixture_path, k=args.k, require_adverse=args.require_adverse)
    failures = threshold_failures(
        report,
        min_supportive_recall=args.min_supportive_recall,
        min_adverse_recall=args.min_adverse_recall,
    )
    report["status"] = "pass" if not failures else "fail"
    report["failures"] = failures
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
