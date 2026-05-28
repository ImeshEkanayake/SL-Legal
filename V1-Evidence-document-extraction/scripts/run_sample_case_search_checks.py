#!/usr/bin/env python3
"""Run sample legal case searches against the hybrid RAG indexes."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tracking" / "sample_case_search_checks"
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.hybrid_retrieval import HybridRetrievalConfig, create_research_pack  # noqa: E402
from sl_legal_rag.models import QueryClass, ResearchQueryRequest, RetrievalFilters  # noqa: E402


@dataclass(frozen=True)
class SampleCase:
    case_id: str
    title: str
    case_facts: str
    query: str
    query_class: QueryClass
    filters: RetrievalFilters
    min_items: int = 3


SAMPLE_CASES = [
    SampleCase(
        case_id="sample_industrial_union_bargaining",
        title="Trade union bargaining refusal",
        case_facts=(
            "A registered trade union says an employer refused to bargain after workers demanded collective "
            "negotiations. The employer threatened transfers and disciplinary action after the union notice."
        ),
        query=(
            "Industrial Disputes Act Sri Lanka employer refusal to bargain trade union collective bargaining "
            "disciplinary transfer workers"
        ),
        query_class=QueryClass.STATUTE_LOOKUP,
        filters=RetrievalFilters(
            language="English",
            document_types=["Act", "Supreme Court Judgment", "Court of Appeal Judgment", "Sri Lanka Law Report", "New Law Report"],
        ),
    ),
    SampleCase(
        case_id="sample_fundamental_rights_arrest",
        title="Arbitrary arrest and detention",
        case_facts=(
            "Police arrested a person without explaining reasons, held him overnight, and did not promptly "
            "produce him before a Magistrate. The family wants fundamental-rights authorities and remedies."
        ),
        query=(
            "Sri Lanka Supreme Court fundamental rights arbitrary arrest detention Article 13 reasons for arrest "
            "produce before Magistrate police"
        ),
        query_class=QueryClass.CASE_LAW_LOOKUP,
        filters=RetrievalFilters(
            language="English",
            document_types=[
                "Supreme Court Judgment",
                "Supreme Court Judgment Archive",
                "Sri Lanka Law Report",
                "New Law Report",
                "Constitution",
            ],
        ),
    ),
    SampleCase(
        case_id="sample_land_acquisition_compensation",
        title="Land acquisition compensation dispute",
        case_facts=(
            "A private land owner received a government acquisition notice for a road project and says the "
            "compensation assessment ignores market value, improvements, and business disruption."
        ),
        query=(
            "Land Acquisition Act Sri Lanka compensation market value acquisition notice road project assessment "
            "appeal"
        ),
        query_class=QueryClass.GENERAL_RESEARCH,
        filters=RetrievalFilters(
            language="English",
            document_types=["Act", "Ordinary Gazette", "Extraordinary Gazette", "Supreme Court Judgment", "Court of Appeal Judgment"],
        ),
    ),
    SampleCase(
        case_id="sample_tax_assessment_appeal",
        title="Income tax assessment appeal",
        case_facts=(
            "A company received an additional income tax assessment and penalty after an audit. It wants to know "
            "appeal steps, objection deadlines, and authorities on assessments."
        ),
        query=(
            "Inland Revenue Act Sri Lanka tax assessment appeal objection notice of assessment penalty company audit"
        ),
        query_class=QueryClass.PROCEDURE,
        filters=RetrievalFilters(
            language="English",
            document_types=["Act", "Ordinary Gazette", "Extraordinary Gazette", "Supreme Court Judgment", "Court of Appeal Judgment"],
        ),
    ),
    SampleCase(
        case_id="sample_local_government_trade_licence",
        title="Local authority trade licence and nuisance",
        case_facts=(
            "A small shop was told by the local authority that its trade licence may be refused due to alleged "
            "public nuisance and by-law violations. The owner wants governing by-laws and appeal material."
        ),
        query=(
            "Sri Lanka local authority by laws trade licence public nuisance municipal council business licence "
            "gazette"
        ),
        query_class=QueryClass.GENERAL_RESEARCH,
        filters=RetrievalFilters(
            language="English",
            document_types=["Ordinary Gazette", "Extraordinary Gazette", "Provincial Statute", "Provincial Legal Framework"],
        ),
    ),
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--candidate-size", type=int, default=40)
    parser.add_argument("--max-items", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=9000)
    return parser.parse_args(argv)


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def fetch_text_version_status(conn: Any, text_version_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not text_version_ids:
        return {}
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                text_version_id, document_id, text_origin, language,
                char_count, text_hash,
                full_text IS NOT NULL AND char_count > 0 AS full_text_available
            FROM document_text_versions
            WHERE text_version_id = ANY(%s)
            """,
            (text_version_ids,),
        )
        rows = cursor.fetchall()
    return {
        str(row[0]): {
            "document_id": row[1],
            "text_origin": row[2],
            "language": row[3],
            "char_count": int(row[4] or 0),
            "text_hash": row[5],
            "full_text_available": bool(row[6]),
        }
        for row in rows
    }


def summarize_pack(conn: Any, sample: SampleCase, pack: Any, elapsed_ms: int) -> dict[str, Any]:
    text_version_ids = [
        str(item.metadata.get("text_version_id") or "")
        for item in pack.items
        if str(item.metadata.get("text_version_id") or "")
    ]
    text_versions = fetch_text_version_status(conn, sorted(set(text_version_ids)))
    top_items = []
    failures = []
    for rank, item in enumerate(pack.items, start=1):
        text_version_id = str(item.metadata.get("text_version_id") or "")
        text_version = text_versions.get(text_version_id)
        full_text_link_ok = bool(text_version and text_version.get("full_text_available"))
        if not text_version_id:
            failures.append(f"item {rank} missing text_version_id")
        elif not full_text_link_ok:
            failures.append(f"item {rank} text_version_id {text_version_id} does not link to full text")
        top_items.append(
            {
                "rank": rank,
                "title": item.title,
                "citation": item.citation,
                "document_type": item.document_type,
                "source_id": item.source_id,
                "authority_level": item.authority_level,
                "year": item.year,
                "fused_score": item.fused_score,
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "text_version_id": text_version_id,
                "full_text_link_ok": full_text_link_ok,
                "text_version_char_count": text_version.get("char_count") if text_version else None,
                "retrieval_evidence": item.metadata.get("retrieval_evidence", []),
                "quality_flags": item.metadata.get("quality_flags", []),
                "snippet": item.text[:360].replace("\n", " "),
            }
        )
    if len(pack.items) < sample.min_items:
        failures.append(f"expected at least {sample.min_items} items, got {len(pack.items)}")
    if pack.missing_source_summary:
        failures.append(f"missing_source_summary: {pack.missing_source_summary}")
    return {
        "case_id": sample.case_id,
        "title": sample.title,
        "query": sample.query,
        "query_class": sample.query_class,
        "elapsed_ms": elapsed_ms,
        "pack_id": pack.pack_id,
        "pack_hash": pack.pack_hash,
        "item_count": len(pack.items),
        "retriever_counts": pack.retrieval_config.get("retriever_counts", {}),
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "top_items": top_items,
    }


def main(argv: list[str]) -> int:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("Missing dependency: run with `uv run --with 'psycopg[binary]'`.") from exc

    args = parse_args(argv)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    packs_dir = output_dir / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)

    base_config = HybridRetrievalConfig.from_settings()
    config = HybridRetrievalConfig(
        opensearch_url=base_config.opensearch_url,
        opensearch_index=base_config.opensearch_index,
        qdrant_url=base_config.qdrant_url,
        qdrant_collection=base_config.qdrant_collection,
        embedding_provider=base_config.embedding_provider,
        embedding_model=base_config.embedding_model,
        embedding_dimensions=base_config.embedding_dimensions,
        candidate_size=args.candidate_size,
    )

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = []
    with psycopg.connect(normalize_psycopg_dsn(args.dsn)) as conn:
        for sample in SAMPLE_CASES:
            start = time.perf_counter()
            request = ResearchQueryRequest(
                query=sample.query,
                query_class=sample.query_class,
                filters=sample.filters,
                max_pack_items=args.max_items,
                max_pack_tokens=args.max_tokens,
                purpose=f"sample_case_search_check:{sample.case_id}",
            )
            pack = create_research_pack(request, config=config)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            pack_path = packs_dir / f"{sample.case_id}.pack.json"
            pack_path.write_text(pack.model_dump_json(indent=2) + "\n", encoding="utf-8")
            results.append(summarize_pack(conn, sample, pack, elapsed_ms))

    report = {
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case_count": len(SAMPLE_CASES),
        "pass_count": sum(1 for result in results if result["status"] == "pass"),
        "fail_count": sum(1 for result in results if result["status"] != "pass"),
        "output_dir": str(output_dir.relative_to(PROJECT_ROOT)),
        "results": results,
    }
    report_path = output_dir / "sample_case_search_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
