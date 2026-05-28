#!/usr/bin/env python3
"""Load-test production two-stage retrieval against a fixture of legal queries."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.two_stage_retrieval import (  # noqa: E402
    DEFAULT_SUMMARY_TYPE,
    TwoStageRetrievalConfig,
    TwoStageRetrievalRequest,
    run_two_stage_retrieval,
)


DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
DEFAULT_FIXTURE = PROJECT_ROOT / "rag" / "evals" / "two_stage_tuned_cases.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "tracking" / "two_stage_load_test.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--stage1-limit", type=int, default=250)
    parser.add_argument("--title-expansion-limit", type=int, default=500)
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--summary-type", default=DEFAULT_SUMMARY_TYPE)
    parser.add_argument("--max-p95-ms", type=float, default=30000.0)
    parser.add_argument("--min-success-rate", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.stage1_limit < 1:
        parser.error("--stage1-limit must be >= 1")
    if args.top_k < 1:
        parser.error("--top-k must be >= 1")
    if not 0 <= args.min_success_rate <= 1:
        parser.error("--min-success-rate must be between 0 and 1")
    return args


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def percentile(values: list[float], percent: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    if percent == 95:
        return float(statistics.quantiles(values, n=20, method="inclusive")[18])
    raise ValueError("only p95 is supported")


def load_requests(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path} must contain a non-empty cases array")
    return [
        {
            "case_id": str(case["case_id"]),
            "query": str(case["query"]),
            "document_types": tuple(str(item) for item in case.get("document_types", ())),
            "language": str(case.get("language", "English")) if case.get("language", "English") is not None else None,
        }
        for case in cases
    ]


def run_request(task: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    import psycopg

    started = time.perf_counter()
    try:
        with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
            result = run_two_stage_retrieval(
                conn,
                TwoStageRetrievalRequest(
                    query=task["query"],
                    document_types=task["document_types"],
                    language=task["language"],
                ),
                TwoStageRetrievalConfig(
                    summary_type=args.summary_type,
                    stage1_limit=args.stage1_limit,
                    title_expansion_limit=args.title_expansion_limit,
                ),
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "case_id": task["case_id"],
            "status": "pass",
            "elapsed_ms": round(elapsed_ms, 3),
            "stage1_candidate_count": len(result.candidates),
            "ranked_document_count": len(result.ranked_documents),
            "top_document_id": result.ranked_documents[0].candidate.document_id if result.ranked_documents else None,
            "top_k_count": len(result.ranked_documents[: args.top_k]),
        }
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "case_id": task["case_id"],
            "status": "fail",
            "elapsed_ms": round(elapsed_ms, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def main(argv: list[str]) -> int:
    try:
        import psycopg  # noqa: F401
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    args = parse_args(argv)
    fixture_path = resolve_project_path(args.fixture)
    output_path = resolve_project_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base_requests = load_requests(fixture_path)
    tasks = base_requests * args.repeat

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(run_request, task, args) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    total_elapsed_ms = (time.perf_counter() - started) * 1000
    durations = [float(item["elapsed_ms"]) for item in results]
    passed = sum(1 for item in results if item["status"] == "pass")
    success_rate = passed / max(1, len(results))
    summary = {
        "status": "pass" if success_rate >= args.min_success_rate and percentile(durations, 95) <= args.max_p95_ms else "fail",
        "fixture_path": str(fixture_path.relative_to(PROJECT_ROOT) if fixture_path.is_relative_to(PROJECT_ROOT) else fixture_path),
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_count": len(results),
        "case_count": len(base_requests),
        "repeat": args.repeat,
        "concurrency": args.concurrency,
        "stage1_limit": args.stage1_limit,
        "title_expansion_limit": args.title_expansion_limit,
        "success_count": passed,
        "failure_count": len(results) - passed,
        "success_rate": round(success_rate, 6),
        "duration_ms": {
            "total_wall": round(total_elapsed_ms, 3),
            "min": round(min(durations), 3) if durations else 0.0,
            "median": round(statistics.median(durations), 3) if durations else 0.0,
            "p95": round(percentile(durations, 95), 3),
            "max": round(max(durations), 3) if durations else 0.0,
        },
        "thresholds": {
            "max_p95_ms": args.max_p95_ms,
            "min_success_rate": args.min_success_rate,
        },
        "results": sorted(results, key=lambda item: (item["case_id"], item["elapsed_ms"])),
    }
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    compact = {key: value for key, value in summary.items() if key != "results"}
    compact["output_path"] = str(output_path.relative_to(PROJECT_ROOT) if output_path.is_relative_to(PROJECT_ROOT) else output_path)
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
