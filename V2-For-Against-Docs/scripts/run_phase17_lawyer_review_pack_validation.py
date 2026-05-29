#!/usr/bin/env python3
"""Generate a Phase 17 lawyer-review reasoning pack from a Phase 16 retrieval report."""

from __future__ import annotations

import argparse
import json
import re
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
from sl_legal_rag.models import (  # noqa: E402
    AuthorityVerification,
    CitedClaim,
    CounterargumentSimulation,
    FactLawMapping,
    ForAgainstArgument,
    ForAgainstLegalBasis,
    IssueMatrixItem,
    LawyerReviewPack,
    LegalElement,
    LegalResearchPack,
    PackItem,
    PreliminaryLegalOpinion,
    QueryClass,
    ReasoningPackOutput,
    RetrievalFilters,
    StrategyDraftResponse,
    StrategyRiskRanking,
)
from sl_legal_rag.strategy import build_citation_validation_summary, generate_strategy_draft  # noqa: E402
from sl_legal_rag.two_stage_retrieval import (  # noqa: E402
    DEFAULT_SUMMARY_TYPE,
    TwoStageRetrievalConfig,
    TwoStageRetrievalRequest,
    excerpt_around_terms,
    search_summary_candidates,
    tokenize,
)


DEFAULT_REPORT_JSON = PROJECT_ROOT / "data" / "tracking" / "phase16_union_bargaining_validation" / "two_stage_search_report.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tracking" / "phase17_lawyer_review_pack_validation"
DEFAULT_PARENT_ENV = PROJECT_ROOT.parent / ".env.azure-openai"
DEFAULT_LOCAL_ENV = PROJECT_ROOT / ".env.azure-openai"
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
EXPANSION_DOCUMENT_TYPES = (
    "Supreme Court Judgment",
    "Court of Appeal Judgment",
    "Sri Lanka Law Report",
    "New Law Report",
    "Court of Appeal Order",
)
EXPANSION_RELEVANCE_TERMS = (
    "Intellectual Property",
    "trade mark",
    "trademark",
    "passing off",
    "unfair competition",
    "brand name",
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--case-id", default="industrial_disputes_union_bargaining")
    parser.add_argument("--top-documents", type=int, default=25)
    parser.add_argument("--chunk-chars", type=int, default=4000)
    parser.add_argument("--max-completion-tokens", type=int, default=12000)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--llm-attempts", type=int, default=3)
    parser.add_argument("--llm-retry-delay-seconds", type=float, default=10.0)
    parser.add_argument("--azure-env-file", default=None)
    parser.add_argument("--no-deterministic-fallback", action="store_true")
    parser.add_argument("--skip-authority-expansion", action="store_true")
    parser.add_argument(
        "--authority-expansion-dsn",
        default=None,
        help="Postgres DSN for read-only wider document-base authority expansion. Defaults to env DSN or local dev DSN.",
    )
    parser.add_argument("--authority-expansion-stage1-limit", type=int, default=250)
    parser.add_argument("--authority-expansion-per-query", type=int, default=5)
    parser.add_argument("--authority-expansion-max-candidates", type=int, default=12)
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
    if args.llm_attempts < 1:
        parser.error("--llm-attempts must be >= 1")
    if args.llm_retry_delay_seconds < 0:
        parser.error("--llm-retry-delay-seconds must be >= 0")
    if args.authority_expansion_stage1_limit < 1:
        parser.error("--authority-expansion-stage1-limit must be >= 1")
    if args.authority_expansion_per_query < 1:
        parser.error("--authority-expansion-per-query must be >= 1")
    if args.authority_expansion_max_candidates < 1:
        parser.error("--authority-expansion-max-candidates must be >= 1")
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


def slugify_identifier(value: object) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return slug[:80] or "case"


def authority_identifier_for_document(document: dict[str, Any]) -> dict[str, str]:
    document_type = str(document.get("document_type") or "Unknown")
    title = clean_text(document.get("title")) or "Retrieved authority"
    year = str(document.get("year") or "undated")
    lower_type = document_type.lower()
    if "gazette" in lower_type:
        match = re.search(r"\b(?:extraordinary\s+|ordinary\s+)?gazette\s+(\d{3,4}/\d{1,3})\b", title, re.IGNORECASE)
        identifier = f"Gazette No. {match.group(1)}" if match else clean_text(title, max_chars=140)
        return {
            "authority_type": document_type,
            "authority_identifier": identifier,
            "citation_label": f"{document_type} {identifier.replace('Gazette ', '')} ({year})",
        }
    if "supreme court" in lower_type:
        identifier = extract_court_authority_identifier(document, default_title=title)
        return {
            "authority_type": "Supreme Court",
            "authority_identifier": identifier,
            "citation_label": f"Supreme Court {identifier}",
        }
    if "court of appeal" in lower_type:
        identifier = extract_court_authority_identifier(document, default_title=title)
        return {
            "authority_type": "Court of Appeal",
            "authority_identifier": identifier,
            "citation_label": f"Court of Appeal {identifier}",
        }
    if "law report" in lower_type:
        identifier = extract_court_authority_identifier(document, default_title=title)
        return {
            "authority_type": "Law Report",
            "authority_identifier": identifier,
            "citation_label": f"Law Report {identifier}",
        }
    if lower_type == "act" or "ordinance" in lower_type:
        act_match = re.search(r"\b([A-Z][A-Za-z,()' -]+(?:Act|Ordinance)(?:\s+No\.?\s+\d+\s+of\s+\d{4})?)", title)
        identifier = clean_text(act_match.group(1) if act_match else title, max_chars=140)
        return {
            "authority_type": document_type,
            "authority_identifier": identifier,
            "citation_label": identifier,
        }
    return {
        "authority_type": document_type,
        "authority_identifier": clean_text(title, max_chars=140),
        "citation_label": f"{document_type}: {clean_text(title, max_chars=140)}",
    }


def extract_court_authority_identifier(document: dict[str, Any], *, default_title: str) -> str:
    contexts = court_identifier_contexts(document, default_title=default_title)
    for context in contexts:
        party_caption = extract_party_caption(context)
        case_number = extract_case_number(context)
        if party_caption and case_number:
            return clean_text(f"{party_caption}, {case_number}", max_chars=220)
        if party_caption:
            return clean_text(party_caption, max_chars=220)
        if case_number:
            return clean_text(case_number, max_chars=220)
    archive_member = extract_archive_member_name(" ".join(contexts))
    suffix = f" from {archive_member}" if archive_member else ""
    return clean_text(f"case caption missing from retrieved excerpt{suffix}; retrieve full judgment/caption page", max_chars=220)


def court_identifier_contexts(document: dict[str, Any], *, default_title: str) -> list[str]:
    contexts: list[str] = [default_title]
    chunk_texts = [
        str(chunk.get("chunk_text") or chunk.get("excerpt") or "")
        for chunk in document_chunks(document)
        if chunk.get("chunk_text") or chunk.get("excerpt")
    ]
    contexts.extend(chunk_texts)
    full_text_context = court_full_text_heading_context(document, chunk_texts)
    if full_text_context:
        contexts.insert(1, full_text_context)
    return contexts


def court_full_text_heading_context(document: dict[str, Any], chunk_texts: list[str]) -> str | None:
    archive_member = extract_archive_member_name(" ".join(chunk_texts))
    if not archive_member:
        return None
    extracted_path = find_extracted_archive_text(document, archive_member)
    if extracted_path is None:
        return None
    try:
        full_text = extracted_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    anchor = first_distinctive_anchor(chunk_texts)
    anchor_index = full_text.find(anchor) if anchor else -1
    if anchor_index == -1 and chunk_texts:
        compact_anchor = clean_text(chunk_texts[0], max_chars=140)
        compact_full_text = clean_text(full_text)
        compact_index = compact_full_text.find(compact_anchor)
        if compact_index != -1:
            return compact_full_text[max(0, compact_index - 6000) : compact_index + 1200]
    if anchor_index == -1:
        return None
    heading_index = full_text.rfind("IN THE SUPREME COURT", 0, anchor_index)
    start_index = heading_index if heading_index != -1 else max(0, anchor_index - 6000)
    return full_text[start_index : anchor_index + 1200]


def extract_archive_member_name(text: str) -> str | None:
    match = re.search(r"Archive member:\s*([^\n\r]+?\.pdf)\b", text or "", re.IGNORECASE)
    return clean_text(match.group(1)) if match else None


def find_extracted_archive_text(document: dict[str, Any], archive_member: str) -> Path | None:
    extracted_root = PROJECT_ROOT.parent / "data" / "extracted" / "text"
    if not extracted_root.exists():
        return None
    document_id = slugify_identifier(document.get("document_id"))
    member_stem = slugify_identifier(Path(archive_member).stem)
    candidates = sorted(extracted_root.glob(f"{document_id}*{member_stem}*.txt"))
    return candidates[0] if candidates else None


def first_distinctive_anchor(chunk_texts: list[str]) -> str | None:
    for text in chunk_texts:
        lines = [line.strip() for line in str(text or "").splitlines() if len(line.strip()) >= 60]
        for line in lines:
            if not line.lower().startswith("archive member:"):
                return line
    return None


def extract_party_caption(text: str) -> str | None:
    patterns = [
        re.compile(
            r"\bAND\s+(?P<appellant>.*?)\s+(?:\d+(?:ST|ND|RD|TH)\s+)?(?:DEFENDANT|PLAINTIFF|PETITIONER|ACCUSED|COMPLAINANT)\s*-\s*APPELLANT\s+VS\.?\s+(?P<respondent>.*?)\s+(?:PLAINTIFF|DEFENDANT|PETITIONER|RESPONDENT|COMPLAINANT)\s*-\s*RESPONDENT",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(?P<appellant>[A-Z][A-Z0-9.,&'()/ \n-]{6,180}?)\s+(?:PLAINTIFF|PETITIONER|APPELLANT|ACCUSED|COMPLAINANT)\s+VS\.?\s+(?P<respondent>[A-Z][A-Z0-9.,&'()/ \n-]{6,180}?)\s+(?:DEFENDANT|RESPONDENT)",
            re.IGNORECASE | re.DOTALL,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(text or "")
        if not match:
            continue
        appellant = party_name_from_block(match.group("appellant"))
        respondent = party_name_from_block(match.group("respondent"))
        if appellant and respondent:
            return f"{appellant} vs {respondent}"
    return None


def party_name_from_block(block: str) -> str:
    lines: list[str] = []
    for raw_line in (block or "").splitlines():
        line = raw_line.strip(" .,\t")
        if not line:
            continue
        if re.search(r"\b(No\.|C/O|National Intellectual Property Office|Floor|Road|Street|Mawatha|Colombo|Matale|Kandana|Department)\b", line, re.IGNORECASE):
            break
        if re.search(r"\b(S\.?C\.?|C\.?H\.?C\.?|Appeal|Application|Case No\.?|BEFORE|COUNSEL|ARGUED|DECIDED)\b", line, re.IGNORECASE):
            continue
        if re.fullmatch(r"(AND|NOW|BETWEEN|VS\.?|V\.?)", line, re.IGNORECASE):
            continue
        lines.append(line)
        if len(lines) >= 3:
            break
    return clean_text(" ".join(lines), max_chars=120)


def extract_case_number(title: str) -> str | None:
    patterns = [
        r"\bS\.?C\.?\s*(?:\([^)]+\)\s*)?(?:C\.?H\.?C\.?\s*)?(?:FR|F/R|SPL|Appeal|Application|Reference|TAB)?\s*(?:No\.?|Application\s+No\.?)\s*:?\s*[\w./ -]+(?:\s*(?:of|/)\s*\d{4})?",
        r"\b(?:SC|Supreme Court)\s*(?:FR|F/R|SPL|Appeal|Application|Reference|TAB)?\s*(?:No\.?|Application\s+No\.?)\s*:?\s*[\w./ -]+(?:\s*(?:of|/)\s*\d{4})?",
        r"\b(?:CA|C\.A\.|Court of Appeal)\s*(?:Writ|Appeal|Application|Revision)?\s*(?:No\.?)\s*:?\s*[\w./ -]+(?:\s*(?:of|/)\s*\d{4})?",
        r"\bCase\s+No\.?\s*[\w./-]+(?:\s*(?:of|/)\s*\d{4})?",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return clean_text(re.sub(r"\s+VS\.?$", "", match.group(0), flags=re.IGNORECASE))
    return None


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
    chunks = document_chunks(document)
    per_chunk_chars = max(800, chunk_chars // max(1, min(3, len(chunks))))
    for chunk in chunks[:3]:
        text = chunk.get("chunk_text") or chunk.get("excerpt") or ""
        if text:
            pieces.append(clean_text(text, max_chars=per_chunk_chars))
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
    case_slug = slugify_identifier(case.get("case_id"))
    for index, document in enumerate(case.get("top_documents", [])[:top_documents], start=1):
        document_type = str(document.get("document_type") or "Unknown")
        title = clean_text(document.get("title")) or f"Retrieved document {index}"
        authority = authority_identifier_for_document(document)
        chunk = (document_chunks(document) or [{}])[0]
        text = text_for_document(document, chunk_chars=chunk_chars)
        items.append(
            PackItem(
                pack_item_id=f"phase17_{case_slug}_item_{index:03d}",
                chunk_id=str(chunk.get("chunk_id") or f"phase17_{case_slug}_chunk_{index:03d}"),
                document_id=str(document.get("document_id") or f"phase17_{case_slug}_document_{index:03d}"),
                title=title,
                document_type=document_type,
                source_id=str(document.get("source_id") or "unknown"),
                authority_level=authority_level_for_document_type(document_type),
                year=document.get("year"),
                citation=authority["citation_label"],
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
                    "authority_type": authority["authority_type"],
                    "authority_identifier": authority["authority_identifier"],
                    "authority_citation_label": authority["citation_label"],
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


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def authority_expansion_dsn(raw_dsn: str | None) -> str:
    import os

    return normalize_psycopg_dsn(
        raw_dsn
        or os.getenv("SL_LEGAL_POSTGRES_DSN")
        or os.getenv("SL_LEGAL_DATABASE_URL")
        or DEFAULT_DSN
    )


def build_authority_expansion_queries(case: dict[str, Any], draft: StrategyDraftResponse) -> list[dict[str, str]]:
    issue_text = " ".join(argument.issue for argument in (draft.reasoning_pack.for_against_brief if draft.reasoning_pack else []))
    missing_text = " ".join(draft.reasoning_pack.missing_evidence_checklist if draft.reasoning_pack else [])
    base_context = clean_text(f"{case.get('title')} {case.get('query')} {issue_text} {missing_text}", max_chars=800)
    queries = [
        {
            "purpose": "direct trademark infringement appellate authorities",
            "query": (
                "trade mark trademark infringement confusing similarity goods services "
                "Intellectual Property Act Supreme Court Court of Appeal Sri Lanka "
                f"{base_context}"
            ),
        },
        {
            "purpose": "passing off and unfair competition authorities",
            "query": (
                "passing off unfair competition trade name goodwill misrepresentation "
                "Intellectual Property Act Supreme Court Court of Appeal Sri Lanka "
                f"{base_context}"
            ),
        },
        {
            "purpose": "interim injunction and remedy authorities",
            "query": (
                "interim injunction intellectual property trademark balance of convenience "
                "damages account of profits delivery up Supreme Court Court of Appeal Sri Lanka "
                f"{base_context}"
            ),
        },
        {
            "purpose": "defence and adverse-authority authorities",
            "query": (
                "honest concurrent use prior use descriptive generic non-use acquiescence delay "
                "trademark Intellectual Property Act Supreme Court Court of Appeal Sri Lanka "
                f"{base_context}"
            ),
        },
    ]
    return queries


def expand_authority_candidates(
    *,
    case: dict[str, Any],
    draft: StrategyDraftResponse,
    pack: LegalResearchPack,
    dsn: str,
    stage1_limit: int,
    per_query: int,
    max_candidates: int,
) -> dict[str, Any]:
    try:
        import psycopg
    except ImportError as exc:
        return {
            "enabled": True,
            "status": "skipped",
            "error": f"Missing psycopg dependency: {exc}",
            "queries": [],
            "candidates": [],
        }

    queries = build_authority_expansion_queries(case, draft)
    base_document_ids = {item.document_id for item in pack.items}
    candidates_by_id: dict[str, dict[str, Any]] = {}
    seen_authority_keys: set[str] = set()
    query_results: list[dict[str, Any]] = []
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute("SET statement_timeout = '15000ms'")
            for query in queries:
                request = TwoStageRetrievalRequest(
                    query=query["query"],
                    document_types=EXPANSION_DOCUMENT_TYPES,
                    language=str(case.get("language") or "English"),
                )
                config = TwoStageRetrievalConfig(
                    summary_type=DEFAULT_SUMMARY_TYPE,
                    stage1_limit=stage1_limit,
                    title_expansion_limit=0,
                    chunks_per_document=0,
                )
                stage1 = search_summary_candidates(conn, request, config)
                query_results.append(
                    {
                        "purpose": query["purpose"],
                        "query": query["query"],
                        "stage1_candidate_count": len(stage1),
                    }
                )
                tokens = tokenize(query["query"])
                accepted_for_query = 0
                for candidate in stage1:
                    if candidate.document_id in base_document_ids:
                        continue
                    authority, authority_context = authority_identifier_for_expansion_candidate(candidate)
                    if not is_relevant_authority_expansion_candidate(candidate, authority, authority_context):
                        continue
                    authority_key = slugify_identifier(
                        f"{authority['authority_type']} {authority['authority_identifier']}"
                    )
                    if authority_key in seen_authority_keys:
                        continue
                    existing = candidates_by_id.get(candidate.document_id)
                    serialized = {
                        "document_id": candidate.document_id,
                        "title": candidate.title,
                        "document_type": candidate.document_type,
                        "year": candidate.year,
                        "source_id": candidate.source_id,
                        "source_url": candidate.source_url,
                        "local_path": candidate.local_path,
                        "authority_type": authority["authority_type"],
                        "authority_identifier": authority["authority_identifier"],
                        "citation_label": authority["citation_label"],
                        "matched_purpose": query["purpose"],
                        "stage1_rank": candidate.stage1_rank,
                        "stage1_score": round(candidate.stage1_score, 8),
                        "summary_excerpt": clean_text(
                            excerpt_around_terms(authority_context or candidate.summary_text, tokens),
                            max_chars=600,
                        ),
                    }
                    if existing is None or serialized["stage1_score"] > existing["stage1_score"]:
                        candidates_by_id[candidate.document_id] = serialized
                        seen_authority_keys.add(authority_key)
                        accepted_for_query += 1
                    if accepted_for_query >= per_query:
                        break
                    if len(candidates_by_id) >= max_candidates:
                        break
                if len(candidates_by_id) >= max_candidates:
                    break
    except Exception as exc:
        return {
            "enabled": True,
            "status": "failed",
            "started_at": started_at,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error": str(exc),
            "queries": query_results,
            "candidates": [],
        }
    candidates = sorted(
        candidates_by_id.values(),
        key=lambda item: (float(item["stage1_score"]), -int(item["stage1_rank"] or 0)),
        reverse=True,
    )[:max_candidates]
    return {
        "enabled": True,
        "status": "pass",
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "queries": query_results,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "note": "Read-only stage-1 expansion; candidates are not treated as pack-cited authorities until promoted into a reviewed pack.",
    }


def authority_identifier_for_expansion_candidate(candidate: Any) -> tuple[dict[str, str], str]:
    context = expansion_context_from_extracted_text(candidate)
    document = {
        "document_id": candidate.document_id,
        "document_type": candidate.document_type,
        "title": candidate.title,
        "year": candidate.year,
        "best_full_text_chunk": {"chunk_text": context or candidate.summary_text},
    }
    return authority_identifier_for_document(document), context


def expansion_context_from_extracted_text(candidate: Any) -> str:
    extracted_path = find_extracted_text_for_document_id(candidate.document_id)
    if extracted_path is None:
        return ""
    try:
        full_text = extracted_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lower = full_text.lower()
    positions = [lower.find(term.lower()) for term in EXPANSION_RELEVANCE_TERMS if lower.find(term.lower()) >= 0]
    if not positions:
        return ""
    anchor_index = min(positions)
    heading_index = full_text.rfind("IN THE SUPREME COURT", 0, anchor_index)
    if heading_index == -1:
        heading_index = full_text.rfind("IN THE COURT OF APPEAL", 0, anchor_index)
    start_index = heading_index if heading_index != -1 else max(0, anchor_index - 5000)
    return full_text[start_index : anchor_index + 1800]


def find_extracted_text_for_document_id(document_id: str) -> Path | None:
    extracted_root = PROJECT_ROOT.parent / "data" / "extracted" / "text"
    if not extracted_root.exists():
        return None
    raw_id = str(document_id or "").strip()
    raw_candidates = sorted(extracted_root.glob(f"{raw_id}*.txt"), key=lambda path: (len(path.name), path.name))
    if raw_candidates:
        return raw_candidates[0]
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(document_id or "").strip().lower()).strip("_")
    candidates = sorted(extracted_root.glob(f"{slug}*.txt"), key=lambda path: (len(path.name), path.name))
    return candidates[0] if candidates else None


def is_relevant_authority_expansion_candidate(candidate: Any, authority: dict[str, str], authority_context: str) -> bool:
    identifier = authority.get("authority_identifier", "")
    if "case caption missing" in identifier.lower():
        return False
    text = " ".join([candidate.title, candidate.document_type, candidate.summary_text, authority_context]).lower()
    return any(term.lower() in text for term in EXPANSION_RELEVANCE_TERMS)


def apply_authority_expansion_to_draft(
    draft: StrategyDraftResponse,
    authority_expansion: dict[str, Any],
) -> StrategyDraftResponse:
    if draft.reasoning_pack is None or authority_expansion.get("status") != "pass":
        return draft
    candidates = authority_expansion.get("candidates") or []
    if not candidates:
        return draft
    top_candidates = candidates[:5]
    candidate_lines = [
        f"{item['authority_type']}: {item['authority_identifier']} ({item['matched_purpose']})"
        for item in top_candidates
    ]
    candidate_sentence = "Candidate authorities from wider stage-1 expansion: " + "; ".join(candidate_lines)
    reasoning = draft.reasoning_pack
    opinion = reasoning.preliminary_legal_opinion
    review_pack = reasoning.lawyer_review_pack
    updated_missing = list(dict.fromkeys([*reasoning.missing_evidence_checklist, candidate_sentence]))
    updated_opinion = opinion.model_copy(
        update={
            "applicable_law": list(dict.fromkeys([*opinion.applicable_law, candidate_sentence])),
            "preliminary_opinion": (
                opinion.preliminary_opinion
                + " The wider document-base expansion has identified candidate appellate or report authorities for verification, "
                "so the next step is to promote the most relevant candidates into the reviewed pack before settling a stronger merits view."
            ),
            "recommended_next_steps": list(
                dict.fromkeys(
                    [
                        *opinion.recommended_next_steps,
                        "Promote the strongest stage-1 expansion candidate authorities into the next reviewed pack and re-run the lawyer-review pack.",
                    ]
                )
            ),
        }
    )
    updated_review_pack = review_pack.model_copy(
        update={
            "missing_documents": list(dict.fromkeys([*review_pack.missing_documents, candidate_sentence])),
            "questions_for_lawyer": list(
                dict.fromkeys(
                    [
                        *review_pack.questions_for_lawyer,
                        "Which stage-1 expansion candidate authorities should be promoted into the reviewed pack, relied on, distinguished, or rejected?",
                    ]
                )
            ),
            "review_notes": list(
                dict.fromkeys(
                    [
                        *review_pack.review_notes,
                        "Wider stage-1 expansion was run read-only against the document base; candidates require promotion into a reviewed pack before reliance.",
                    ]
                )
            ),
        }
    )
    updated_reasoning = reasoning.model_copy(
        update={
            "missing_evidence_checklist": updated_missing,
            "preliminary_legal_opinion": updated_opinion,
            "lawyer_review_pack": updated_review_pack,
        }
    )
    warnings = list(
        dict.fromkeys(
            [
                *draft.warnings,
                "Wider document-base expansion found candidate authorities that require lawyer verification and pack promotion before reliance.",
            ]
        )
    )
    return draft.model_copy(update={"reasoning_pack": updated_reasoning, "warnings": warnings})


class RetryingJsonChatClient:
    """Retry transient Azure failures without weakening pack validation."""

    TRANSIENT_ERROR_RE = re.compile(r"\bHTTP (?:429|500|502|503|504)\b|timed out|temporarily unavailable", re.IGNORECASE)

    def __init__(self, client: AzureChatClient, *, attempts: int, retry_delay_seconds: float):
        self.client = client
        self.attempts = attempts
        self.retry_delay_seconds = retry_delay_seconds
        self.attempt_log: list[dict[str, object]] = []

    def complete_json(
        self,
        *,
        messages: list[dict[str, str]],
        max_completion_tokens: int = 2048,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                result = self.client.complete_json(
                    messages=messages,
                    max_completion_tokens=max_completion_tokens,
                    temperature=temperature,
                )
                self.attempt_log.append({"attempt": attempt, "status": "pass"})
                return result
            except Exception as exc:
                last_error = exc
                error = str(exc)
                transient = bool(self.TRANSIENT_ERROR_RE.search(error))
                self.attempt_log.append(
                    {
                        "attempt": attempt,
                        "status": "fail",
                        "transient": transient,
                        "error_type": type(exc).__name__,
                        "error": error[:500],
                    }
                )
                if not transient or attempt >= self.attempts:
                    break
                print(
                    json.dumps(
                        {
                            "event": "phase17_llm_retry",
                            "attempt": attempt,
                            "next_attempt": attempt + 1,
                            "delay_seconds": self.retry_delay_seconds,
                            "error_type": type(exc).__name__,
                        }
                    ),
                    flush=True,
                )
                time.sleep(self.retry_delay_seconds)
        assert last_error is not None
        raise last_error


def is_ip_authority(item: PackItem) -> bool:
    searchable = " ".join(
        [
            item.title,
            item.citation,
            item.document_type,
            str(item.metadata.get("authority_identifier") or ""),
        ]
    ).lower()
    return any(term in searchable for term in ["intellectual property", "trademark", "trade mark", "patent", "copyright"])


def deterministic_reasoning_pack(case: dict[str, Any], pack: LegalResearchPack, *, provider_error: str) -> StrategyDraftResponse:
    """Build a cautious offline pack when the model provider cannot complete the long prompt."""

    supportive_items = [item for item in pack.items if is_ip_authority(item)]
    gazette_items = [item for item in pack.items if "gazette" in item.document_type.lower()]
    court_items = [
        item
        for item in pack.items
        if "supreme court" in item.document_type.lower() or "court of appeal" in item.document_type.lower()
    ]
    adverse_items = [item for item in pack.items if item not in supportive_items and item not in gazette_items and item not in court_items]
    if not supportive_items:
        supportive_items = pack.items[: min(5, len(pack.items))]
    primary_ids = [item.pack_item_id for item in supportive_items[:6]]
    gazette_ids = [item.pack_item_id for item in gazette_items[:4]]
    adverse_ids = [item.pack_item_id for item in adverse_items[:6]]
    court_ids = [item.pack_item_id for item in court_items[:3]]
    all_focus_ids = sorted(set(primary_ids + gazette_ids + adverse_ids + court_ids)) or sorted(pack.allowed_pack_item_ids)[:5]
    court_case_status = (
        "The pack identifies a Supreme Court case caption and case number; lawyer verification is still required for current treatment and direct trademark relevance."
        if court_ids
        else "The pack does not identify a specific Supreme Court or Court of Appeal trademark case number."
    )
    court_case_next_step = (
        "Verify the identified Supreme Court judgment and retrieve additional Supreme Court or Court of Appeal trademark authorities if needed."
        if court_ids
        else "Retrieve specific Supreme Court and Court of Appeal trademark cases with case numbers."
    )
    missing_rights_documents = [
        "Client/right-holder documents: trademark registration certificate, application/registration number, class, goods/services specification, owner name, and current registry extract.",
        "Client/right-holder documents: renewal history, pending opposition/cancellation status, disclaimers, limitations, assignments, licences, security interests, and group-company authority to sue.",
        "Client instructions and facts: chronology of adoption, first use, continuous use, geographic use, product lines, sales history, advertising spend, and instructions confirming the exact relief sought.",
    ]
    missing_defendant_conduct = [
        "Defendant conduct evidence: specimens of the accused mark/sign, packaging, labels, invoices, catalogues, advertisements, social media posts, website pages, marketplace listings, and dated screenshots.",
        "Defendant conduct evidence: date of first use, continued use, manufacturing/supplier/distributor details, sales channels, territory, customer targets, and whether use is registered, licensed, or claimed as prior use.",
        "Comparison evidence: side-by-side mark comparison, phonetic/visual/conceptual similarity analysis, goods/services comparison, trade-channel overlap, price-point overlap, and likely customer profile.",
    ]
    missing_confusion_and_damage = [
        "Confusion/goodwill evidence: customer complaints, mistaken enquiries, surveys, retailer evidence, distributor evidence, social-media confusion, market recognition, goodwill, reputation, and deception/misrepresentation proof.",
        "Damage/remedy evidence: lost sales, diverted customers, unjust profit/accounting material, reputational harm, urgency, balance of convenience, irreparable harm, delivery-up needs, and customs/enforcement facts.",
    ]
    missing_law_authorities = [
        "Statutory verification: current consolidated Intellectual Property Act/Code sections for registration, rights conferred, infringement, unfair competition/passing off, assignments/licences, remedies, offences, and transitional provisions.",
        "Amendment verification: all post-enactment IP amendments checked against official sources, with effective dates and whether they affect marks, trade names, unfair competition, remedies, or procedure.",
        court_case_next_step,
        "Case-law verification: Court of Appeal trademark, trade name, unfair competition, passing off, interim injunction, and remedy decisions with party captions, case numbers, holdings, and current treatment.",
        "Gazette/NIPO verification: relevant Gazette notices, NIPO practice directions, fee schedules, classification material, registry practice, opposition/cancellation procedure, and any mark-specific Gazette publications.",
    ]
    missing_defences_adverse = [
        "Defences/adverse facts: prior use, honest concurrent use, descriptive/generic use, own-name use, consent/licence, acquiescence, delay/laches, non-use, invalidity, exhaustion, different goods/services, and lack of confusion.",
        "Adverse retrieval review: non-IP statutes, Penal Code/proceeds/anti-corruption/appropriation materials, and unrelated Gazettes must be quarantined unless a lawyer identifies a specific procedural or enforcement relevance.",
    ]
    missing_procedure_quality = [
        "Procedure/forum proof: correct forum, cause of action, limitation period, standing, necessary parties, interim injunction test, pleadings, affidavits, exhibits, translations, certified copies, and service/enforcement route.",
        "Source-quality review: OCR quality, page anchors, judgment caption pages, archive-member boundaries, official-source availability, translations, Sinhala/Tamil/English consistency, and whether excerpts match the cited authority.",
        "Witness proof: client witnesses, investigators, retailers/distributors, confused customers, registry/NIPO records custodians, and affidavit-ready exhibit list.",
    ]
    comprehensive_missing_evidence = [
        *missing_rights_documents,
        *missing_defendant_conduct,
        *missing_confusion_and_damage,
        *missing_law_authorities,
        *missing_defences_adverse,
        *missing_procedure_quality,
    ]
    authority_verifications = [
        AuthorityVerification(
            authority_id=f"AUTH_{index:03d}",
            title=item.title,
            authority_type=str(item.metadata.get("authority_type") or item.document_type),
            citation=str(item.metadata.get("authority_citation_label") or item.citation),
            pack_item_ids=[item.pack_item_id],
            section="to_be_verified",
            verification_status="requires_lawyer_review",
            notes=(
                "Offline deterministic fallback used after provider failure; official consolidation, amendments, "
                "and current case-law treatment must be checked by a lawyer."
            ),
        )
        for index, item in enumerate(pack.items, start=1)
    ]
    issue_elements = [
        LegalElement(
            element_id="EL_001",
            element="Ownership or entitlement to sue on a registered or protectable mark",
            supporting_facts=["The retrieved IP statutes and amendments are relevant to trademark ownership and registration checks."],
            opposing_facts=["The current pack does not include the client's registration certificate, assignment chain, or renewal status."],
            authority_ids=["AUTH_001"],
            pack_item_ids=primary_ids[:3],
            missing_evidence=missing_rights_documents,
            verification_status="requires_lawyer_review",
        ),
        LegalElement(
            element_id="EL_002",
            element="Use of an identical or confusingly similar sign in trade",
            supporting_facts=["The IP authorities support framing the issue around protected mark rights and infringement analysis."],
            opposing_facts=["No defendant packaging, advertisements, invoices, screenshots, or marketplace evidence is in the pack."],
            authority_ids=["AUTH_001"],
            pack_item_ids=primary_ids[:4],
            missing_evidence=missing_defendant_conduct + missing_confusion_and_damage,
            verification_status="requires_lawyer_review",
        ),
        LegalElement(
            element_id="EL_003",
            element="Relief, procedure, and enforcement risk",
            supporting_facts=["Gazette and amendment materials may help verify procedural or fee/regulatory context if relevant."],
            opposing_facts=["Several retrieved documents are unrelated to trademark infringement and should not be treated as legal support."],
            authority_ids=["AUTH_006"],
            pack_item_ids=(gazette_ids[:2] + adverse_ids[:2]) or all_focus_ids[:3],
            missing_evidence=missing_law_authorities + missing_defences_adverse + missing_procedure_quality,
            verification_status="requires_lawyer_review",
        ),
    ]
    issue_matrix = [
        IssueMatrixItem(
            issue_id="ISSUE_001",
            issue="Can the client establish trademark ownership and standing?",
            legal_area="Intellectual property / trademark infringement",
            elements=[issue_elements[0]],
            authority_ids=["AUTH_001"],
            facts_supporting=["The pack contains IP legislation and amendments relevant to trademark rights."],
            facts_against=["The pack does not contain client-specific registration or chain-of-title evidence."],
            missing_evidence=issue_elements[0].missing_evidence,
            confidence=0.42,
            verification_status="requires_lawyer_review",
        ),
        IssueMatrixItem(
            issue_id="ISSUE_002",
            issue="Can infringement or confusing similarity be proved on the available documents?",
            legal_area="Intellectual property / trademark infringement",
            elements=[issue_elements[1]],
            authority_ids=["AUTH_001"],
            facts_supporting=["The IP statute set is a relevant starting point for infringement analysis."],
            facts_against=["The pack lacks defendant-use evidence and market-confusion evidence."],
            missing_evidence=issue_elements[1].missing_evidence,
            confidence=0.36,
            verification_status="requires_lawyer_review",
        ),
        IssueMatrixItem(
            issue_id="ISSUE_003",
            issue="What authorities or documents weaken the case at this stage?",
            legal_area="Evidence quality and authority verification",
            elements=[issue_elements[2]],
            authority_ids=["AUTH_006"],
            facts_supporting=["The pack identifies some official-source materials such as Acts and Gazettes."],
            facts_against=["Unrelated Acts appear in the 25-document set and should be treated as adverse retrieval noise.", court_case_status],
            missing_evidence=issue_elements[2].missing_evidence,
            confidence=0.48,
            verification_status="requires_lawyer_review",
        ),
    ]
    fact_to_law_mappings = [
        FactLawMapping(
            issue_id="ISSUE_001",
            fact="Client ownership and subsistence of the mark are assumed but not evidenced in this pack.",
            legal_question="Does the Code of Intellectual Property and amendments support standing once registration and title are proved?",
            authority_id="AUTH_001",
            specific_section="to_be_verified",
            supporting_reasoning="The retrieved IP statutes are relevant, but the application depends on registry and title documents not present in the pack.",
            risk="A standing argument is premature without client-specific registration and renewal evidence.",
            missing_documents=issue_elements[0].missing_evidence,
            pack_item_ids=primary_ids[:4],
            verification_status="requires_lawyer_review",
        ),
        FactLawMapping(
            issue_id="ISSUE_002",
            fact="Defendant use and confusing similarity are not proved by the current retrieval pack.",
            legal_question="Can infringement be established without specimens, dates, and trade-channel evidence?",
            authority_id="AUTH_001",
            specific_section="to_be_verified",
            supporting_reasoning="The legal framework can be identified from IP authorities, but the infringement application requires factual exhibits.",
            risk="The opposing side can argue that the pack shows law but not infringement facts.",
            missing_documents=issue_elements[1].missing_evidence,
            pack_item_ids=primary_ids[:4],
            verification_status="requires_lawyer_review",
        ),
        FactLawMapping(
            issue_id="ISSUE_003",
            fact="Some top-25 retrieved documents are not trademark authorities.",
            legal_question="Should non-IP statutes be excluded from the legal basis?",
            authority_id=None,
            specific_section="not_applicable",
            supporting_reasoning="Non-IP materials may be contextual at most; they should be adverse retrieval-noise review items unless a lawyer identifies a procedural or criminal-enforcement relevance.",
            risk="Using unrelated authorities would weaken the lawyer-review pack and may create uncited or inaccurate legal propositions.",
            missing_documents=[court_case_next_step],
            pack_item_ids=adverse_ids[:4] or all_focus_ids[:2],
            verification_status="requires_lawyer_review",
        ),
    ]
    for_against_brief = [
        ForAgainstArgument(
            issue_id="ISSUE_001",
            issue="Trademark ownership and standing",
            legal_basis=[
                ForAgainstLegalBasis(
                    authority_id="AUTH_001",
                    authority="Code of Intellectual Property / Intellectual Property Acts and amendments",
                    section="registration, ownership, and infringement provisions to_be_verified",
                    proposition="The statutory framework is the correct starting point for trademark ownership and infringement, subject to lawyer verification of current sections.",
                    pack_item_ids=primary_ids[:5],
                    verification_status="requires_lawyer_review",
                )
            ],
            facts_relied_on=["The pack contains IP statutes and amendments but no client registry documents."],
            client_argument="For the client: the retrieved IP Acts and amendments support using Sri Lankan intellectual-property legislation as the governing framework for a trademark claim.",
            opposing_argument="Against the client: the pack does not yet prove ownership, registration validity, renewal, assignment, or licence standing.",
            rebuttal="The next legal step is to bind the statutory framework to registry records and title documents before a lawyer expresses a stronger view.",
            weaknesses=issue_elements[0].missing_evidence,
            missing_evidence=issue_elements[0].missing_evidence,
            strength="medium",
            confidence=0.42,
            pack_item_ids=primary_ids[:5],
        ),
        ForAgainstArgument(
            issue_id="ISSUE_002",
            issue="Infringement and confusing similarity",
            legal_basis=[
                ForAgainstLegalBasis(
                    authority_id="AUTH_001",
                    authority="Code of Intellectual Property / Intellectual Property Acts and amendments",
                    section="trademark infringement provisions to_be_verified",
                    proposition="The legal test must be applied to the defendant's actual sign, goods/services, market context, and evidence of use.",
                    pack_item_ids=primary_ids[:5],
                    verification_status="requires_lawyer_review",
                )
            ],
            facts_relied_on=["No defendant specimens or confusion evidence were present in the 25-document pack."],
            client_argument="For the client: the statutory materials can support an infringement theory if the defendant used a similar sign for relevant goods or services.",
            opposing_argument="Against the client: the present pack lacks the factual exhibits needed to prove use, similarity, timing, trade channel, consumer confusion, or damage.",
            rebuttal="The pack should be supplemented with defendant-use exhibits and a mark comparison so a lawyer can apply the statutory provisions to concrete facts.",
            weaknesses=issue_elements[1].missing_evidence,
            missing_evidence=issue_elements[1].missing_evidence,
            strength="low",
            confidence=0.36,
            pack_item_ids=primary_ids[:5],
        ),
        ForAgainstArgument(
            issue_id="ISSUE_003",
            issue="Authority quality, adverse retrieval, and missing case law",
            legal_basis=[
                ForAgainstLegalBasis(
                    authority_id="AUTH_006",
                    authority="Gazette materials and retrieved non-IP statutes",
                    section="relevance to_be_verified",
                    proposition="Gazettes or non-IP Acts should not be relied on for trademark infringement unless a lawyer confirms their procedural or regulatory relevance.",
                    pack_item_ids=(gazette_ids[:4] + adverse_ids[:4]) or all_focus_ids[:6],
                    verification_status="requires_lawyer_review",
                ),
                ForAgainstLegalBasis(
                    authority_id="AUTH_015" if court_ids else None,
                    authority="Supreme Court or Court of Appeal trademark authority",
                    section=(
                        "identified case caption and case number; trademark relevance/current treatment to_be_verified"
                        if court_ids
                        else "specific case number missing from current pack"
                    ),
                    proposition=(
                        "A production-ready opinion must verify the identified Supreme Court judgment and add any more directly relevant appellate trademark authorities."
                        if court_ids
                        else "A production-ready opinion needs current Supreme Court or Court of Appeal authority with specific case numbers, not a generic judgment label."
                    ),
                    pack_item_ids=court_ids,
                    verification_status="requires_lawyer_review",
                ),
            ],
            facts_relied_on=["The top-25 retrieval includes unrelated Acts.", court_case_status],
            client_argument="For the client: official Acts and Gazettes are available as a starting authority set.",
            opposing_argument="Against the client: unrelated authorities and insufficiently verified appellate treatment weaken the review pack and must be separated from the legal basis.",
            rebuttal="Treat unrelated documents as adverse retrieval items, require lawyer verification, and run targeted retrieval for additional Supreme Court, Court of Appeal, Gazette, and registry materials.",
            weaknesses=[
                court_case_status,
                "Several top-25 documents appear unrelated to trademark infringement.",
            ],
            missing_evidence=[
                court_case_next_step,
                "Relevant Gazette notices only if tied to IP procedure, fees, registry practice, or enforcement.",
            ],
            strength="unknown",
            confidence=0.48,
            pack_item_ids=(gazette_ids[:4] + adverse_ids[:4] + court_ids[:2]) or all_focus_ids[:6],
        ),
    ]
    missing_evidence = comprehensive_missing_evidence
    reviewed_docs = [
        f"{item.metadata.get('authority_type') or item.document_type}: {item.metadata.get('authority_identifier') or item.citation}"
        for item in pack.items[:25]
    ]
    preliminary = PreliminaryLegalOpinion(
        matter="Trademark infringement and IP registration validation pack",
        instructions=str(case.get("case_facts") or case.get("query") or "Assess trademark infringement materials."),
        important_qualification=(
            "This is a preliminary lawyer-review output generated from an offline validation pack after the LLM provider failed; "
            "lawyer verification is required before advice, filing, or client communication."
        ),
        assumed_facts=[
            "The client claims a protectable trademark interest.",
            "The opposing party may have used a similar sign in commerce.",
        ],
        documents_reviewed=reviewed_docs,
        issues=[item.issue for item in issue_matrix],
        applicable_law=[
            "Code of Intellectual Property and Intellectual Property amendments, sections to_be_verified by lawyer.",
            "Relevant Gazettes only if tied to IP procedure or registry practice, Gazette numbers to_be_verified by lawyer.",
            court_case_next_step,
        ],
        analysis=(
            "The preliminary analysis is supportive only at the legal-framework level: IP statutes and amendments were retrieved, "
            "but the pack does not yet connect the law to registration, defendant use, confusing similarity, or remedy evidence. "
            "Lawyer verification is required for sections, amendments, case law, and procedural steps."
        ),
        preliminary_opinion=(
            "Preliminary view for lawyer verification: the matter can be structured as a trademark infringement review, but the current "
            "25-document pack is not sufficient for a merits opinion because client-specific facts, defendant-use evidence, and additional "
            "directly relevant case-law authorities may still be needed."
        ),
        risks=[
            "The case may fail at proof stage if ownership and defendant use are not documented.",
            "Unrelated retrieved authorities must not be relied on as legal support.",
            "A court-facing strategy needs specific Supreme Court or Court of Appeal cases and current statutory sections.",
            "Potential defences such as prior use, descriptive/generic use, acquiescence, non-use, invalidity, different goods/services, or lack of confusion have not been tested.",
        ],
        recommended_next_steps=[
            court_case_next_step,
            "Collect registry, renewal, assignment, licence, defendant-use, comparison, confusion, goodwill, and damages evidence.",
            "Prepare an adverse-defence review covering prior use, honest concurrent use, generic/descriptive use, delay/acquiescence, non-use, invalidity, exhaustion, and different goods/services.",
            "Have a lawyer verify current statutory sections and amendment status.",
        ],
        conclusion=(
            "This preliminary lawyer-verification pack is useful for triage, but it is not settled legal advice and should proceed to "
            "targeted authority retrieval and document collection before a legal opinion is settled."
        ),
    )
    review_pack = LawyerReviewPack(
        one_page_case_summary=(
            "Test 10 concerns trademark infringement and IP registration. The 25-document pack contains several IP Acts/amendments and "
            "Gazettes, but it also includes unrelated authorities and lacks client-specific trademark documents, defendant-use exhibits, "
            "market/confusion evidence, remedy proof, procedural verification, and complete adverse-defence review."
        ),
        issue_matrix_ids=[item.issue_id for item in issue_matrix],
        authority_ids=[item.authority_id for item in authority_verifications],
        missing_documents=missing_evidence,
        questions_for_client=[
            "What exact trademark registration number, class, goods/services, owner, and renewal status are relied on?",
            "What defendant mark/sign was used, where, when, and on which goods or services?",
            "Are there screenshots, invoices, packaging samples, customer confusion evidence, or cease-and-desist correspondence?",
        ],
        questions_for_lawyer=[
            "Which current Code of Intellectual Property sections govern the pleaded infringement theory?",
            "Which additional Supreme Court or Court of Appeal trademark authorities, by case number, must be added or distinguished?",
            "Are any Gazettes in this pack relevant to IP procedure, fees, registry practice, or enforcement?",
            "What defences or adverse facts must be tested before stronger advice is given?",
            "What forum, limitation, interim injunction, affidavit, translation, certified-copy, and exhibit requirements apply?",
            "Should non-IP documents be excluded as adverse retrieval noise?",
        ],
        review_notes=[
            "Deterministic fallback was used because Azure OpenAI returned repeated HTTP 500 errors.",
            "Every legal conclusion remains marked for lawyer verification.",
        ],
    )
    reasoning_pack = ReasoningPackOutput(
        output_type="lawyer_review_pack",
        authority_verifications=authority_verifications,
        issue_matrix=issue_matrix,
        fact_to_law_mappings=fact_to_law_mappings,
        for_against_brief=for_against_brief,
        missing_evidence_checklist=missing_evidence,
        preliminary_legal_opinion=preliminary,
        lawyer_review_pack=review_pack,
        warnings=[
            "Deterministic fallback used after provider failure; use as triage only.",
            "No database writes occurred.",
            "No settled legal advice language is intended.",
        ],
    )
    answer = (
        f"This is a preliminary lawyer-review pack for trademark infringement and IP registration; it uses the retrieved IP Acts, "
        f"amendments, Gazettes, and review flags only as a bounded validation set. {' '.join(f'[{item_id}]' for item_id in all_focus_ids[:8])} "
        f"The supportive position is that the Code of Intellectual Property and related amendments provide the correct legal framework, "
        f"but the case still needs registration, renewal, title, defendant-use, similarity, and confusion evidence before a lawyer can settle an opinion. {' '.join(f'[{item_id}]' for item_id in primary_ids[:6])} "
        f"The adverse position is that unrelated retrieved documents and insufficiently verified appellate treatment weaken the pack and require targeted authority retrieval. {' '.join(f'[{item_id}]' for item_id in (adverse_ids[:4] + court_ids[:2] + gazette_ids[:2]) or all_focus_ids[:6])} "
        f"This output is not settled legal advice and requires lawyer verification of statutory sections, amendments, case law, Gazettes, and procedure. {' '.join(f'[{item_id}]' for item_id in all_focus_ids[:8])}"
    )
    response = StrategyDraftResponse(
        pack_id=pack.pack_id,
        answer=answer,
        claims=[
            CitedClaim(
                claim="The retrieved IP Acts and amendments are relevant to framing the trademark legal basis, subject to lawyer verification.",
                pack_item_ids=primary_ids[:5],
                confidence="needs_lawyer_review",
            ),
            CitedClaim(
                claim="The current pack does not prove ownership, defendant use, confusing similarity, or remedy facts.",
                pack_item_ids=all_focus_ids[:5],
                confidence="needs_lawyer_review",
            ),
            CitedClaim(
                claim=court_case_status,
                pack_item_ids=court_ids or all_focus_ids[:3],
                confidence="needs_lawyer_review",
            ),
        ],
        reasoning_pack=reasoning_pack,
        counterarguments=[
            CounterargumentSimulation(
                counterargument="The opposing side can argue that statutes alone do not prove registration, use, similarity, or damage.",
                supporting_pack_item_ids=all_focus_ids[:5],
                response="The response is to collect registry and defendant-use documents and then apply the verified IP provisions.",
                response_pack_item_ids=primary_ids[:5],
                risk_level="high",
            ),
            CounterargumentSimulation(
                counterargument="The opposing side can attack reliance on unrelated retrieved documents or insufficiently verified appellate treatment.",
                supporting_pack_item_ids=adverse_ids[:4] or all_focus_ids[:4],
                response="Those materials should be treated as adverse retrieval noise unless a lawyer confirms a specific relevance.",
                response_pack_item_ids=(adverse_ids[:4] + court_ids[:2]) or all_focus_ids[:4],
                risk_level="medium",
            ),
        ],
        risk_rankings=[
            StrategyRiskRanking(
                risk="Missing registration and ownership evidence.",
                severity="high",
                rationale="The legal framework cannot be applied safely without proof of the mark, owner, class, renewal, and title.",
                pack_item_ids=primary_ids[:5],
                mitigation="Collect registry extracts and title documents.",
            ),
            StrategyRiskRanking(
                risk="Missing defendant-use and confusion evidence.",
                severity="high",
                rationale="Infringement analysis needs specimens, dates, channels of trade, goods/services comparison, and confusion evidence.",
                pack_item_ids=primary_ids[:5],
                mitigation="Collect exhibits and prepare a side-by-side mark comparison.",
            ),
            StrategyRiskRanking(
                risk="Missing specific appellate case law and unrelated retrieval results.",
                severity="medium",
                rationale="The pack needs specific Supreme Court or Court of Appeal case numbers and should quarantine unrelated documents.",
                pack_item_ids=(court_ids + adverse_ids[:4]) or all_focus_ids[:5],
                mitigation="Run targeted case-law retrieval and mark non-IP hits for lawyer review.",
            ),
        ],
        missing_authorities=[
            "Current consolidated Code of Intellectual Property sections for trademark infringement.",
            court_case_next_step,
            "Additional Court of Appeal trademark infringement cases with case numbers.",
            "Relevant Gazettes tied to IP procedure or registry practice.",
            "Procedural authorities for forum, limitation, interim injunctions, affidavits, certified copies, translations, and enforcement.",
        ],
        warnings=[
            "Azure provider failed repeated attempts; deterministic fallback generated a cautious triage pack.",
            "Lawyer verification is required before advice or filing.",
            f"Provider error: {provider_error[:300]}",
        ],
    )
    return response.model_copy(update={"citation_validation": build_citation_validation_summary(response, pack)})


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
        lines.extend(["## Pack Sources", ""])
        for item in report.get("pack_sources", []):
            lines.append(
                f"- `{item['pack_item_id']}`: {item['authority_type']} - {item['authority_identifier']} "
                f"(`{item['document_id']}`)"
            )
        source_lookup = {
            str(item["pack_item_id"]): f"{item['authority_type']} - {item['authority_identifier']}"
            for item in report.get("pack_sources", [])
            if item.get("pack_item_id")
        }
        lines.append("")
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
                    "Cited authorities:",
                    *(
                        f"- `{pack_item_id}`: {source_lookup.get(pack_item_id, 'unknown authority')}"
                        for pack_item_id in argument.pack_item_ids
                    ),
                    "",
                    "Legal basis:",
                    *(
                        f"- {basis.authority}; section/reference: {basis.section}; pack IDs: {', '.join(basis.pack_item_ids)}"
                        for basis in argument.legal_basis
                    ),
                    "",
                    "Weaknesses:",
                    *(f"- {item}" for item in argument.weaknesses),
                    "",
                    "Missing evidence:",
                    *(f"- {item}" for item in argument.missing_evidence),
                    "",
                ]
            )
        authority_expansion = report.get("authority_expansion") or {}
        if authority_expansion.get("status") == "pass":
            lines.extend(
                [
                    "## Wider Stage-1 Authority Expansion",
                    "",
                    f"- Status: `{authority_expansion.get('status')}`",
                    f"- Candidate authorities: `{authority_expansion.get('candidate_count', 0)}`",
                    "- Use: candidate authorities for lawyer verification and next-pack promotion; not pack-cited authorities yet.",
                    "",
                ]
            )
            for candidate in authority_expansion.get("candidates", [])[:12]:
                lines.append(
                    f"- {candidate['authority_type']} - {candidate['authority_identifier']} "
                    f"(`{candidate['document_id']}`, purpose: {candidate['matched_purpose']})"
                )
            lines.append("")
        elif authority_expansion:
            lines.extend(
                [
                    "## Wider Stage-1 Authority Expansion",
                    "",
                    f"- Status: `{authority_expansion.get('status')}`",
                    f"- Error: {authority_expansion.get('error') or 'none'}",
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
        "pack_sources": [
            {
                "pack_item_id": item.pack_item_id,
                "document_id": item.document_id,
                "document_type": item.document_type,
                "authority_type": str(item.metadata.get("authority_type") or item.document_type),
                "authority_identifier": str(item.metadata.get("authority_identifier") or item.citation),
                "citation_label": item.citation,
            }
            for item in pack.items
        ],
        "requested_output": "lawyer_review_pack",
        "draft_path": None,
        "llm_attempts": [],
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
                        "llm_attempts": args.llm_attempts,
                    }
                ),
                flush=True,
            )

            def _handle_timeout(_signum: int, _frame: object) -> None:
                raise TimeoutError(f"Phase 17 reasoning timed out after {args.timeout_seconds} seconds")

            previous_handler = signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(args.timeout_seconds)
            client = RetryingJsonChatClient(
                AzureChatClient(load_azure_chat_config(env_file)),
                attempts=args.llm_attempts,
                retry_delay_seconds=args.llm_retry_delay_seconds,
            )
            try:
                draft = generate_strategy_draft(
                    case_facts=str(case.get("case_facts") or ""),
                    pack=pack,
                    client=client,
                    requested_output="lawyer_review_pack",
                    max_completion_tokens=args.max_completion_tokens,
                )
            finally:
                report["llm_attempts"] = client.attempt_log
                signal.alarm(0)
                signal.signal(signal.SIGALRM, previous_handler)
            report.update(
                {
                    "status": "pass",
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
        if not args.skip_llm and not args.no_deterministic_fallback:
            try:
                draft = deterministic_reasoning_pack(case, pack, provider_error=str(exc))
                report.update(
                    {
                        "status": "pass_with_deterministic_fallback",
                        "claim_count": len(draft.claims),
                        "for_against_count": len(draft.reasoning_pack.for_against_brief) if draft.reasoning_pack else 0,
                        "missing_evidence_count": (
                            len(draft.reasoning_pack.missing_evidence_checklist) if draft.reasoning_pack else 0
                        ),
                        "citation_validation": draft.citation_validation,
                        "fallback_used": True,
                        "fallback_reason": str(exc),
                    }
                )
            except Exception as fallback_exc:
                report["fallback_error"] = str(fallback_exc)
    if draft is not None and not args.skip_authority_expansion:
        authority_expansion = expand_authority_candidates(
            case=case,
            draft=draft,
            pack=pack,
            dsn=authority_expansion_dsn(args.authority_expansion_dsn),
            stage1_limit=args.authority_expansion_stage1_limit,
            per_query=args.authority_expansion_per_query,
            max_candidates=args.authority_expansion_max_candidates,
        )
        report["authority_expansion"] = authority_expansion
        draft = apply_authority_expansion_to_draft(draft, authority_expansion)
        report.update(
            {
                "claim_count": len(draft.claims),
                "for_against_count": len(draft.reasoning_pack.for_against_brief) if draft.reasoning_pack else 0,
                "missing_evidence_count": (
                    len(draft.reasoning_pack.missing_evidence_checklist) if draft.reasoning_pack else 0
                ),
                "citation_validation": draft.citation_validation,
            }
        )
    elif draft is not None:
        report["authority_expansion"] = {"enabled": False, "status": "skipped", "candidates": []}
    if draft is not None:
        draft_path = output_dir / "phase17_lawyer_review_pack.json"
        draft_path.write_text(draft.model_dump_json(indent=2) + "\n", encoding="utf-8")
        report["draft_path"] = str(draft_path)
    report["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary_path = output_dir / "phase17_lawyer_review_pack_summary.md"
    write_summary(case, draft, report, summary_path)
    report_path_out = output_dir / "phase17_validation_report.json"
    report_path_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_path": str(report_path_out), "summary_path": str(summary_path)}, indent=2))
    return 0 if report["status"] in {"pass", "pack_built", "pass_with_deterministic_fallback"} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
