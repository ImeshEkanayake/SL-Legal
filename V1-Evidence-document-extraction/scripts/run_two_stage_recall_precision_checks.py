#!/usr/bin/env python3
"""Evaluate two-stage legal retrieval against an external fixture file.

The retrieval engine lives in ``sl_legal_rag.two_stage_retrieval``. This runner
only loads grading fixtures, resolves expected authorities, and writes reports.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.two_stage_retrieval import (  # noqa: E402
    DEFAULT_SUMMARY_TYPE,
    RankedDocument,
    SummaryCandidate,
    TwoStageRetrievalConfig,
    TwoStageRetrievalRequest,
    run_two_stage_retrieval,
    serialize_ranked_document,
    tokenize,
    to_prefix_tsquery,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tracking" / "two_stage_sample_case_search_checks"
DEFAULT_FIXTURE = PROJECT_ROOT / "rag" / "evals" / "two_stage_tuned_cases.json"
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"


@dataclass(frozen=True)
class ExpectedSelector:
    label: str
    document_ids: tuple[str, ...] = ()
    title_like: str | None = None
    document_types: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    text_query: str | None = None
    limit: int = 10


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    title: str
    case_facts: str
    query: str
    document_types: tuple[str, ...]
    expected_selectors: tuple[ExpectedSelector, ...]
    language: str = "English"
    stage1_limit: int | None = None
    expected_count: int = 10


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="JSON fixture with cases and expected authorities.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--stage1-limit", type=int, default=750)
    parser.add_argument("--title-expansion-limit", type=int, default=1500)
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--summary-type", default=DEFAULT_SUMMARY_TYPE)
    parser.add_argument("--min-stage1-expected-recall", type=float, default=0.90)
    parser.add_argument("--min-top-k-expected-recall", type=float, default=1.0)
    return parser.parse_args(argv)


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_fixture(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path} must contain a non-empty 'cases' array")
    loaded: list[EvalCase] = []
    for raw_case in cases:
        selectors = []
        for raw_selector in raw_case.get("expected_selectors", []):
            selector_ids = tuple(str(item) for item in raw_selector.get("document_ids", ()))
            selectors.append(
                ExpectedSelector(
                    label=str(raw_selector["label"]),
                    document_ids=selector_ids,
                    title_like=raw_selector.get("title_like"),
                    document_types=tuple(str(item) for item in raw_selector.get("document_types", ())),
                    source_ids=tuple(str(item) for item in raw_selector.get("source_ids", ())),
                    text_query=raw_selector.get("text_query"),
                    limit=int(raw_selector.get("limit", max(10, len(selector_ids) or 10))),
                )
            )
        fixed_documents = raw_case.get("expected_documents", [])
        if fixed_documents:
            selectors.insert(
                0,
                ExpectedSelector(
                    label="Fixture expected documents",
                    document_ids=tuple(str(item["document_id"] if isinstance(item, dict) else item) for item in fixed_documents),
                    limit=len(fixed_documents),
                ),
            )
        if not selectors:
            raise ValueError(f"{path}: case {raw_case.get('case_id')} has no expected documents or selectors")
        loaded.append(
            EvalCase(
                case_id=str(raw_case["case_id"]),
                title=str(raw_case["title"]),
                case_facts=str(raw_case.get("case_facts", "")),
                query=str(raw_case["query"]),
                document_types=tuple(str(item) for item in raw_case.get("document_types", ())),
                expected_selectors=tuple(selectors),
                language=str(raw_case.get("language", "English")) if raw_case.get("language", "English") is not None else None,
                stage1_limit=raw_case.get("stage1_limit"),
                expected_count=int(raw_case.get("expected_count", 10)),
            )
        )
    return loaded


def resolve_expected_documents(conn: Any, case: EvalCase, *, summary_type: str) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    seen: set[str] = set()
    with conn.cursor() as cursor:
        for selector in case.expected_selectors:
            if selector.document_ids:
                cursor.execute(
                    """
                    SELECT
                        d.document_id,
                        d.title,
                        d.document_type,
                        d.year,
                        d.source_id,
                        d.language
                    FROM documents d
                    JOIN document_summaries ds ON ds.document_id = d.document_id
                    JOIN document_text_versions dtv ON dtv.text_version_id = ds.text_version_id
                    WHERE d.document_id = ANY(%(document_ids)s)
                      AND ds.summary_type = %(summary_type)s
                      AND dtv.full_text IS NOT NULL
                      AND dtv.char_count > 0
                    ORDER BY array_position(%(document_ids)s::text[], d.document_id)
                    """,
                    {"document_ids": list(selector.document_ids), "summary_type": summary_type},
                )
                for row in cursor.fetchall():
                    document_id = str(row[0])
                    if document_id in seen:
                        continue
                    seen.add(document_id)
                    expected.append(
                        {
                            "document_id": document_id,
                            "title": row[1],
                            "document_type": row[2],
                            "year": row[3],
                            "source_id": row[4],
                            "language": row[5],
                            "selector": selector.label,
                        }
                    )
                    if len(expected) >= case.expected_count:
                        return expected
                continue
            tokens = tokenize(selector.text_query or selector.title_like or case.query)
            tsquery = to_prefix_tsquery(tokens)
            clauses = [
                "ds.summary_type = %(summary_type)s",
                "d.acquisition_status = 'downloaded'",
                "dtv.full_text IS NOT NULL",
                "dtv.char_count > 0",
            ]
            params: dict[str, Any] = {
                "summary_type": summary_type,
                "language": case.language,
                "limit": selector.limit,
                "tsquery": tsquery,
            }
            if case.language:
                clauses.append("(d.language = %(language)s OR ds.language = %(language)s OR dtv.language = %(language)s)")
            if selector.title_like:
                clauses.append("d.title ILIKE %(title_like)s")
                params["title_like"] = selector.title_like
            if selector.document_types:
                clauses.append("d.document_type = ANY(%(document_types)s)")
                params["document_types"] = list(selector.document_types)
            if selector.source_ids:
                clauses.append("d.source_id = ANY(%(source_ids)s)")
                params["source_ids"] = list(selector.source_ids)
            if selector.text_query:
                clauses.append("to_tsvector('simple', ds.summary_text) @@ to_tsquery('simple', %(tsquery)s)")
            cursor.execute(
                f"""
                WITH scored AS (
                    SELECT
                        d.document_id,
                        d.title,
                        d.document_type,
                        d.year,
                        d.source_id,
                        d.language,
                        ts_rank_cd(to_tsvector('simple', ds.summary_text), to_tsquery('simple', %(tsquery)s), 32) AS summary_rank,
                        ts_rank_cd(to_tsvector('simple', d.title), to_tsquery('simple', %(tsquery)s), 32) AS title_rank,
                        CASE
                            WHEN d.document_type IN ('Constitution', 'Core Legislation', 'Act') THEN 0
                            WHEN d.document_type LIKE '%%Judgment%%' THEN 1
                            WHEN d.document_type LIKE '%%Gazette%%' THEN 2
                            ELSE 3
                        END AS type_priority
                    FROM documents d
                    JOIN document_summaries ds ON ds.document_id = d.document_id
                    JOIN document_text_versions dtv ON dtv.text_version_id = ds.text_version_id
                    WHERE {" AND ".join(clauses)}
                ),
                deduped AS (
                    SELECT *,
                        row_number() OVER (
                            PARTITION BY document_id
                            ORDER BY (summary_rank + (3 * title_rank)) DESC, year DESC NULLS LAST, title
                        ) AS rn
                    FROM scored
                )
                SELECT
                    document_id,
                    title,
                    document_type,
                    year,
                    source_id,
                    language,
                    summary_rank,
                    title_rank
                FROM deduped
                WHERE rn = 1
                ORDER BY
                    type_priority,
                    (summary_rank + (3 * title_rank)) DESC,
                    year DESC NULLS LAST,
                    title
                LIMIT %(limit)s
                """,
                params,
            )
            for row in cursor.fetchall():
                document_id = str(row[0])
                if document_id in seen:
                    continue
                seen.add(document_id)
                expected.append(
                    {
                        "document_id": document_id,
                        "title": row[1],
                        "document_type": row[2],
                        "year": row[3],
                        "source_id": row[4],
                        "language": row[5],
                        "selector": selector.label,
                    }
                )
                if len(expected) >= case.expected_count:
                    return expected
    return expected


def metric_summary(expected_ids: set[str], stage1: list[SummaryCandidate], final: list[RankedDocument], *, top_k: int) -> dict[str, Any]:
    stage1_ids = [candidate.document_id for candidate in stage1]
    final_ids = [item.candidate.document_id for item in final[:top_k]]
    stage1_found = expected_ids.intersection(stage1_ids)
    top_found = expected_ids.intersection(final_ids)
    return {
        "expected_count": len(expected_ids),
        "stage1_found_count": len(stage1_found),
        "top_k_found_count": len(top_found),
        "stage1_expected_recall": round(len(stage1_found) / max(1, len(expected_ids)), 6),
        "top_k_expected_recall": round(len(top_found) / max(1, len(expected_ids)), 6),
        "missing_from_stage1": sorted(expected_ids - stage1_found),
        "missing_from_top_k": sorted(expected_ids - top_found),
    }


def expected_document_status(
    expected_docs: list[dict[str, Any]],
    stage1: list[SummaryCandidate],
    final: list[RankedDocument],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    stage1_rank = {candidate.document_id: candidate.stage1_rank for candidate in stage1}
    final_rank = {item.candidate.document_id: item.final_rank for item in final}
    final_score = {item.candidate.document_id: item.relevance_score for item in final}
    statuses = []
    for doc in expected_docs:
        document_id = doc["document_id"]
        statuses.append(
            {
                **doc,
                "found_in_stage1": document_id in stage1_rank,
                "stage1_rank": stage1_rank.get(document_id),
                "found_in_final_top_k": final_rank.get(document_id, math.inf) <= top_k,
                "final_rank": None if document_id not in final_rank else final_rank[document_id],
                "final_relevance_score": final_score.get(document_id),
            }
        )
    return statuses


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Two-Stage Recall/Precision Search Check",
        "",
        f"- Fixture: `{report['fixture_path']}`",
        f"- Started: `{report['started_at']}`",
        f"- Completed: `{report['completed_at']}`",
        f"- Cases: `{report['case_count']}`",
        f"- Pass: `{report['pass_count']}`",
        f"- Fail: `{report['fail_count']}`",
        f"- Stage 1 limit: `{report['stage1_limit']}`",
        f"- Final top K: `{report['top_k']}`",
        "",
        "## Case Results",
        "",
    ]
    for case in report["cases"]:
        metrics = case["metrics"]
        lines.extend(
            [
                f"### {case['title']}",
                "",
                f"- Status: `{case['status']}`",
                f"- Stage 1 candidates: `{case['stage1_candidate_count']}`",
                f"- Expected docs resolved: `{metrics['expected_count']}`",
                f"- Expected found in stage 1: `{metrics['stage1_found_count']}` / `{metrics['expected_count']}`",
                f"- Expected found in top {report['top_k']}: `{metrics['top_k_found_count']}` / `{metrics['expected_count']}`",
                f"- Elapsed: `{case['elapsed_ms']} ms`",
                "",
                "| Rank | Score | Expected | Type | Year | Title | Summary abstract |",
                "|---:|---:|:---:|---|---:|---|---|",
            ]
        )
        for item in case["top_documents"][:10]:
            summary = str(item["summary_search_excerpt"]).replace("|", "\\|")
            if len(summary) > 260:
                summary = summary[:257] + "..."
            title = str(item["title"]).replace("|", "\\|")
            lines.append(
                f"| {item['rank']} | {item['relevance_score']} | {'yes' if item['expected_document'] else ''} "
                f"| {item['document_type']} | {item['year'] or ''} | {title} | {summary} |"
            )
        if case["failures"]:
            lines.extend(["", "Failures:"])
            for failure in case["failures"]:
                lines.append(f"- {failure}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_case(conn: Any, case: EvalCase, args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    expected_docs = resolve_expected_documents(conn, case, summary_type=args.summary_type)
    expected_ids = {doc["document_id"] for doc in expected_docs}
    request = TwoStageRetrievalRequest(query=case.query, document_types=case.document_types, language=case.language)
    config = TwoStageRetrievalConfig(
        summary_type=args.summary_type,
        stage1_limit=args.stage1_limit or case.stage1_limit or 750,
        title_expansion_limit=args.title_expansion_limit,
    )
    result = run_two_stage_retrieval(conn, request, config)
    for item in result.ranked_documents:
        item.metadata["expected"] = item.candidate.document_id in expected_ids
    metrics = metric_summary(expected_ids, result.candidates, result.ranked_documents, top_k=args.top_k)
    failures: list[str] = []
    if len(expected_docs) < case.expected_count:
        failures.append(f"expected document set resolved only {len(expected_docs)} docs; wanted {case.expected_count}")
    if metrics["stage1_expected_recall"] < args.min_stage1_expected_recall:
        failures.append(
            f"stage1 expected recall {metrics['stage1_expected_recall']} below {args.min_stage1_expected_recall}"
        )
    if metrics["top_k_expected_recall"] < args.min_top_k_expected_recall:
        failures.append(
            f"top-{args.top_k} expected recall {metrics['top_k_expected_recall']} below {args.min_top_k_expected_recall}"
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    top_documents = []
    for item in result.ranked_documents[: args.top_k]:
        serialized = serialize_ranked_document(item, query=case.query, tokens=result.tokens)
        serialized["expected_document"] = item.candidate.document_id in expected_ids
        top_documents.append(serialized)
    return {
        "case_id": case.case_id,
        "title": case.title,
        "case_facts": case.case_facts,
        "query": case.query,
        "document_types": list(case.document_types),
        "language": case.language,
        "elapsed_ms": elapsed_ms,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "stage1_candidate_count": len(result.candidates),
        "metrics": metrics,
        "expected_documents": expected_document_status(expected_docs, result.candidates, result.ranked_documents, top_k=args.top_k),
        "top_documents": top_documents,
        "title_hints": result.title_hints,
    }


def main(argv: list[str]) -> int:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    args = parse_args(argv)
    fixture_path = resolve_project_path(args.fixture)
    output_dir = resolve_project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases_to_run = load_fixture(fixture_path)

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cases: list[dict[str, Any]] = []
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        for case in cases_to_run:
            print(f"running {case.case_id}...", file=sys.stderr, flush=True)
            cases.append(run_case(conn, case, args))

    report = {
        "fixture_path": str(fixture_path.relative_to(PROJECT_ROOT) if fixture_path.is_relative_to(PROJECT_ROOT) else fixture_path),
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case_count": len(cases),
        "pass_count": sum(1 for case in cases if case["status"] == "pass"),
        "fail_count": sum(1 for case in cases if case["status"] != "pass"),
        "stage1_limit": args.stage1_limit,
        "title_expansion_limit": args.title_expansion_limit,
        "top_k": args.top_k,
        "minimums": {
            "stage1_expected_recall": args.min_stage1_expected_recall,
            "top_k_expected_recall": args.min_top_k_expected_recall,
        },
        "cases": cases,
    }
    report_path = output_dir / "two_stage_search_report.json"
    summary_path = output_dir / "two_stage_search_summary.md"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown_report(report, summary_path)
    compact = {
        "report_path": str(report_path.relative_to(PROJECT_ROOT) if report_path.is_relative_to(PROJECT_ROOT) else report_path),
        "summary_path": str(summary_path.relative_to(PROJECT_ROOT) if summary_path.is_relative_to(PROJECT_ROOT) else summary_path),
        "fixture_path": report["fixture_path"],
        "case_count": report["case_count"],
        "pass_count": report["pass_count"],
        "fail_count": report["fail_count"],
        "cases": [
            {
                "case_id": case["case_id"],
                "status": case["status"],
                "stage1_candidates": case["stage1_candidate_count"],
                "stage1_expected_recall": case["metrics"]["stage1_expected_recall"],
                "top_k_expected_recall": case["metrics"]["top_k_expected_recall"],
                "failures": case["failures"],
            }
            for case in cases
        ],
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
