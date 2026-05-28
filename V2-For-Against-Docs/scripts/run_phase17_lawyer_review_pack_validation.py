#!/usr/bin/env python3
"""Generate a Phase 17 lawyer-review reasoning pack from a Phase 16 retrieval report."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.llm import AzureChatClient, load_azure_chat_config  # noqa: E402
from sl_legal_rag.models import LegalResearchPack, PackItem, QueryClass, RetrievalFilters  # noqa: E402
from sl_legal_rag.strategy import generate_strategy_draft  # noqa: E402


DEFAULT_REPORT_JSON = PROJECT_ROOT / "data" / "tracking" / "phase16_union_bargaining_validation" / "two_stage_search_report.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tracking" / "phase17_lawyer_review_pack_validation"
DEFAULT_PARENT_ENV = PROJECT_ROOT.parent / ".env.azure-openai"
DEFAULT_LOCAL_ENV = PROJECT_ROOT / ".env.azure-openai"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--case-id", default="industrial_disputes_union_bargaining")
    parser.add_argument("--top-documents", type=int, default=10)
    parser.add_argument("--chunk-chars", type=int, default=1800)
    parser.add_argument("--max-completion-tokens", type=int, default=12000)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--azure-env-file", default=None)
    parser.add_argument("--skip-llm", action="store_true", help="Build the research pack and report config without calling Azure.")
    args = parser.parse_args(argv)
    if args.top_documents < 1:
        parser.error("--top-documents must be >= 1")
    if args.chunk_chars < 500:
        parser.error("--chunk-chars must be >= 500")
    if args.max_completion_tokens < 2000:
        parser.error("--max-completion-tokens must be >= 2000")
    if args.timeout_seconds < 30:
        parser.error("--timeout-seconds must be >= 30")
    return args


def resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def authority_level_for_document_type(document_type: str) -> int:
    lower = document_type.lower()
    if "constitution" in lower:
        return 1
    if lower == "act" or "ordinance" in lower:
        return 2
    if "judgment" in lower or "law report" in lower:
        return 3
    if "gazette" in lower:
        return 4
    if "bill" in lower:
        return 5
    return 6


def clean_text(value: object, *, max_chars: int | None = None) -> str:
    text = " ".join(str(value or "").split())
    if max_chars and len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def document_chunks(document: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    seen: set[str] = set()
    best = document.get("best_full_text_chunk")
    if isinstance(best, dict):
        chunks.append(best)
        if best.get("chunk_id"):
            seen.add(str(best["chunk_id"]))
    for raw_chunk in document.get("evidence_chunks") or []:
        if not isinstance(raw_chunk, dict):
            continue
        chunk_id = str(raw_chunk.get("chunk_id") or "")
        if chunk_id and chunk_id in seen:
            continue
        if chunk_id:
            seen.add(chunk_id)
        chunks.append(raw_chunk)
    return chunks


def text_for_document(document: dict[str, Any], *, chunk_chars: int) -> str:
    pieces: list[str] = []
    for chunk in document_chunks(document)[:2]:
        page_start = chunk.get("page_start")
        page_end = chunk.get("page_end") or page_start
        heading = f"Pages {page_start}-{page_end}: " if page_start else ""
        text = chunk.get("chunk_text") or chunk.get("excerpt") or ""
        if text:
            pieces.append(heading + clean_text(text, max_chars=chunk_chars // 2))
    if not pieces:
        pieces.append(clean_text(document.get("summary_search_excerpt"), max_chars=chunk_chars))
    return clean_text(" ".join(pieces), max_chars=chunk_chars)


def load_case(report_path: Path, *, case_id: str) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for case in report.get("cases", []):
        if str(case.get("case_id")) == case_id:
            return case
    raise ValueError(f"case_id not found in report: {case_id}")


def pack_from_case(case: dict[str, Any], *, top_documents: int, chunk_chars: int) -> LegalResearchPack:
    items: list[PackItem] = []
    for index, document in enumerate(case.get("top_documents", [])[:top_documents], start=1):
        document_type = str(document.get("document_type") or "Unknown")
        title = clean_text(document.get("title")) or f"Retrieved document {index}"
        chunk = (document_chunks(document) or [{}])[0]
        text = text_for_document(document, chunk_chars=chunk_chars)
        items.append(
            PackItem(
                pack_item_id=f"phase17_union_item_{index:03d}",
                chunk_id=str(chunk.get("chunk_id") or f"phase17_chunk_{index:03d}"),
                document_id=str(document.get("document_id") or f"phase17_document_{index:03d}"),
                title=title,
                document_type=document_type,
                source_id=str(document.get("source_id") or "unknown"),
                authority_level=authority_level_for_document_type(document_type),
                year=document.get("year"),
                citation=f"{title} ({document.get('year') or 'undated'})",
                page_start=chunk.get("page_start"),
                page_end=chunk.get("page_end"),
                text=text,
                fused_score=float(document.get("relevance_score") or 0),
                selection_reason="Phase 17 validation pack item generated from Phase 16 two-stage retrieval output.",
                source_url=document.get("source_url"),
                local_path=document.get("local_path"),
                token_estimate=max(1, len(text) // 4),
                scoring_breakdown=dict(document.get("scoring_breakdown") or {}),
                retrieval_trace=[
                    {
                        "phase": "phase16_two_stage_retrieval",
                        "rank": document.get("rank"),
                        "expected_document": bool(document.get("expected_document")),
                        "relevance_score": document.get("relevance_score"),
                    }
                ],
                metadata={
                    "phase": "phase17_lawyer_review_pack_validation",
                    "expected_document": bool(document.get("expected_document")),
                },
            )
        )
    if not items:
        raise ValueError("retrieval case did not contain top_documents")
    return LegalResearchPack(
        pack_id=f"phase17_{case.get('case_id')}_pack",
        query=str(case.get("query") or ""),
        query_class=QueryClass.STRATEGY,
        filters=RetrievalFilters(document_types=list(case.get("document_types") or []), language=case.get("language") or "English"),
        retrieval_config={
            "source": "phase16_two_stage_search_report",
            "top_documents": top_documents,
            "chunk_chars": chunk_chars,
        },
        items=items,
        missing_source_summary=(
            "This validation pack is generated from the Phase 16 offline retrieval report. "
            "It is Gazette-heavy and requires lawyer verification for current law, amendments, case law, procedure, and client documents."
        ),
        token_count=sum(item.token_estimate or 0 for item in items),
        source_warnings=[
            "Offline validation pack only; not a final legal opinion.",
            "No database draft or review item is persisted by this script.",
        ],
        retrieval_trace=[{"phase": "phase17_pack_from_phase16_report", "case_id": case.get("case_id")}],
    )


def resolve_azure_env_file(raw_path: str | None) -> Path | None:
    if raw_path:
        return resolve_project_path(raw_path)
    if DEFAULT_LOCAL_ENV.exists():
        return DEFAULT_LOCAL_ENV
    if DEFAULT_PARENT_ENV.exists():
        return DEFAULT_PARENT_ENV
    return None


def write_summary(case: dict[str, Any], draft: Any | None, report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Phase 17 Lawyer Review Pack Validation",
        "",
        f"- Case ID: `{case.get('case_id')}`",
        f"- Status: `{report['status']}`",
        f"- Requested output: `lawyer_review_pack`",
        f"- Pack items: `{report['pack_item_count']}`",
        f"- Database writes: `none`",
        "",
    ]
    if draft is None or draft.reasoning_pack is None:
        lines.extend(["## Result", "", report.get("error") or "No reasoning pack was generated.", ""])
    else:
        reasoning = draft.reasoning_pack
        lines.extend(
            [
                "## For / Against Brief",
                "",
            ]
        )
        for index, argument in enumerate(reasoning.for_against_brief, start=1):
            lines.extend(
                [
                    f"### Argument {index}: {argument.issue}",
                    "",
                    f"- For: {argument.client_argument}",
                    f"- Against: {argument.opposing_argument}",
                    f"- Rebuttal: {argument.rebuttal}",
                    f"- Strength: `{argument.strength}`",
                    f"- Confidence: `{argument.confidence}`",
                    f"- Lawyer verification required: `{argument.requires_lawyer_verification}`",
                    "",
                    "Weaknesses:",
                    *(f"- {item}" for item in argument.weaknesses),
                    "",
                    "Missing evidence:",
                    *(f"- {item}" for item in argument.missing_evidence),
                    "",
                ]
            )
        lines.extend(
            [
                "## Missing Evidence Checklist",
                "",
                *(f"- {item}" for item in reasoning.missing_evidence_checklist),
                "",
                "## Preliminary Opinion",
                "",
                reasoning.preliminary_legal_opinion.important_qualification,
                "",
                reasoning.preliminary_legal_opinion.preliminary_opinion,
                "",
                "## Lawyer Review Questions",
                "",
                "Questions for client:",
                *(f"- {item}" for item in reasoning.lawyer_review_pack.questions_for_client),
                "",
                "Questions for lawyer:",
                *(f"- {item}" for item in reasoning.lawyer_review_pack.questions_for_lawyer),
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report_path = resolve_project_path(args.report_json)
    output_dir = resolve_project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    case = load_case(report_path, case_id=args.case_id)
    pack = pack_from_case(case, top_documents=args.top_documents, chunk_chars=args.chunk_chars)
    pack_path = output_dir / "phase17_research_pack.json"
    pack_path.write_text(pack.model_dump_json(indent=2) + "\n", encoding="utf-8")

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    draft = None
    report: dict[str, Any] = {
        "status": "pack_built" if args.skip_llm else "failed",
        "started_at": started_at,
        "completed_at": None,
        "case_id": args.case_id,
        "pack_path": str(pack_path),
        "pack_item_count": len(pack.items),
        "requested_output": "lawyer_review_pack",
        "draft_path": None,
        "summary_path": str(output_dir / "phase17_lawyer_review_pack_summary.md"),
        "error": None,
    }
    try:
        if args.skip_llm:
            report["error"] = "LLM call skipped by --skip-llm."
        else:
            env_file = resolve_azure_env_file(args.azure_env_file)
            print(
                json.dumps(
                    {
                        "event": "phase17_reasoning_start",
                        "case_id": args.case_id,
                        "pack_items": len(pack.items),
                        "max_completion_tokens": args.max_completion_tokens,
                    }
                ),
                flush=True,
            )

            def _handle_timeout(_signum: int, _frame: object) -> None:
                raise TimeoutError(f"Phase 17 reasoning timed out after {args.timeout_seconds} seconds")

            previous_handler = signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(args.timeout_seconds)
            client = AzureChatClient(load_azure_chat_config(env_file))
            try:
                draft = generate_strategy_draft(
                    case_facts=str(case.get("case_facts") or ""),
                    pack=pack,
                    client=client,
                    requested_output="lawyer_review_pack",
                    max_completion_tokens=args.max_completion_tokens,
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous_handler)
            draft_path = output_dir / "phase17_lawyer_review_pack.json"
            draft_path.write_text(draft.model_dump_json(indent=2) + "\n", encoding="utf-8")
            report.update(
                {
                    "status": "pass",
                    "draft_path": str(draft_path),
                    "claim_count": len(draft.claims),
                    "for_against_count": len(draft.reasoning_pack.for_against_brief) if draft.reasoning_pack else 0,
                    "missing_evidence_count": (
                        len(draft.reasoning_pack.missing_evidence_checklist) if draft.reasoning_pack else 0
                    ),
                    "citation_validation": draft.citation_validation,
                }
            )
    except Exception as exc:
        report["status"] = "fail"
        report["error"] = str(exc)
    report["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary_path = output_dir / "phase17_lawyer_review_pack_summary.md"
    write_summary(case, draft, report, summary_path)
    report_path_out = output_dir / "phase17_validation_report.json"
    report_path_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_path": str(report_path_out), "summary_path": str(summary_path)}, indent=2))
    return 0 if report["status"] in {"pass", "pack_built"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
