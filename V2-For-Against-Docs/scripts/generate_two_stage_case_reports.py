#!/usr/bin/env python3
"""Generate color-coded PDF-ready LaTeX reports from two-stage retrieval output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

DEFAULT_REPORT_JSON = PROJECT_ROOT / "data" / "tracking" / "two_stage_sample_case_search_checks" / "two_stage_search_report.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tracking" / "two_stage_sample_case_search_checks" / "pdf_reports"
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
REPORT_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "under",
    "about",
    "after",
    "before",
    "between",
    "where",
    "which",
    "case",
    "legal",
    "sri",
    "lanka",
    "ceylon",
    "act",
    "acts",
    "law",
    "laws",
    "section",
    "article",
    "ordinance",
}


@dataclass(frozen=True)
class DocumentPalette:
    frame: str
    back: str
    title: str


PALETTES = {
    "act": DocumentPalette("ActFrame", "ActBack", "ActTitle"),
    "bill": DocumentPalette("BillFrame", "BillBack", "BillTitle"),
    "gazette": DocumentPalette("GazetteFrame", "GazetteBack", "GazetteTitle"),
    "supreme_court": DocumentPalette("SupremeFrame", "SupremeBack", "SupremeTitle"),
    "court_of_appeal": DocumentPalette("AppealFrame", "AppealBack", "AppealTitle"),
    "law_report": DocumentPalette("ReportFrame", "ReportBack", "ReportTitle"),
    "constitution": DocumentPalette("ConstitutionFrame", "ConstitutionBack", "ConstitutionTitle"),
    "other": DocumentPalette("OtherFrame", "OtherBack", "OtherTitle"),
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN") or os.getenv("SL_LEGAL_DATABASE_URL") or DEFAULT_DSN)
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--case-id", action="append", default=[], help="Generate only the matching case ID. May be repeated.")
    parser.add_argument("--top-documents", type=int, default=25)
    parser.add_argument("--chunk-chars", type=int, default=1200)
    parser.add_argument("--include-summary-abstract", action="store_true", help="Include the stage-1 summary-search abstract in each evidence box.")
    parser.add_argument("--fetch-full-chunk-text", action="store_true", help="Fetch complete retrieval chunk text from Postgres when the report JSON only has excerpts.")
    parser.add_argument("--compile", action="store_true", help="Compile generated TeX files to PDF with latexmk or pdflatex.")
    parser.add_argument("--compiler", choices=("auto", "tectonic", "latexmk", "pdflatex"), default="auto")
    parser.add_argument("--clean-evidence-text", action="store_true", help="Clean OCR/evidence snippets with an LLM before rendering.")
    parser.add_argument(
        "--conservative-clean-evidence-text",
        action="store_true",
        help="Clean obvious OCR artifacts without an LLM; never rewrites substance.",
    )
    parser.add_argument("--clean-cache", default=None, help="JSON cache for cleaned evidence snippets.")
    parser.add_argument("--clean-input-chars", type=int, default=1800)
    parser.add_argument("--azure-account-name", default=os.getenv("AZURE_OPENAI_ACCOUNT_NAME", ""))
    parser.add_argument("--azure-deployment-name", default=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", ""))
    parser.add_argument("--azure-chat-completions-url", default=os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_URL", ""))
    parser.add_argument("--azure-api-version", default=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"))
    args = parser.parse_args(argv)
    if args.top_documents < 1:
        parser.error("--top-documents must be >= 1")
    if args.chunk_chars < 200:
        parser.error("--chunk-chars must be >= 200")
    if args.clean_input_chars < 400:
        parser.error("--clean-input-chars must be >= 400")
    if args.clean_evidence_text and args.conservative_clean_evidence_text:
        parser.error("choose either --clean-evidence-text or --conservative-clean-evidence-text, not both")
    return args


def resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return slug[:120] or "case_report"


def ascii_clean(text: object) -> str:
    value = "" if text is None else str(text)
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value.encode("ascii", "replace").decode("ascii")


def latex_escape(text: object) -> str:
    value = ascii_clean(text)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def normalize_text(text: object, *, max_chars: int | None = None) -> str:
    value = re.sub(r"\s+", " ", ascii_clean(text)).strip()
    if max_chars and len(value) > max_chars:
        return value[: max_chars - 3].rstrip() + "..."
    return value


def report_query_tokens(query: object) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9]{2,}", ascii_clean(query).lower()):
        token = match.group(0)
        if token in REPORT_STOPWORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens[:24]


def extractive_summary(text: object, *, query: object, max_chars: int) -> str:
    value = normalize_text(text)
    if not value or len(value) <= max_chars:
        return value
    tokens = report_query_tokens(query)
    lower = value.lower()
    positions = [lower.find(token) for token in tokens if lower.find(token) >= 0]
    if not positions:
        return normalize_text(value, max_chars=max_chars)
    center = min(positions)
    radius = max(120, max_chars // 2)
    start = max(0, center - radius)
    end = min(len(value), center + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(value) else ""
    return f"{prefix}{value[start:end].strip()}{suffix}"


def clean_metadata_text(text: object, *, max_chars: int | None = None) -> str:
    value = normalize_text(text)
    value = re.sub(r"\?+\s*\"", "-", value)
    value = re.sub(r"\s+([,.;:])", r"\1", value)
    value = re.sub(r"\bAct\.No\.", "Act No.", value)
    value = re.sub(r"\bP\s+\.\s+Councils\b", "P. Councils", value)
    return normalize_text(value, max_chars=max_chars)


def clipped_text_for_cleaning(text: object, *, max_chars: int) -> str:
    return normalize_text(text, max_chars=max_chars)


def safe_cleaned_text(original: str, cleaned: str) -> str:
    candidate = normalize_text(cleaned)
    source = normalize_text(original)
    if not candidate:
        return source
    refusal_markers = ("cannot", "can't", "unable", "as an ai", "i'm sorry", "i am sorry")
    if any(marker in candidate.lower()[:160] for marker in refusal_markers):
        return source
    if len(candidate) > max(len(source) * 1.35, len(source) + 350):
        return source
    return candidate


class EvidenceTextCleaner:
    def clean(self, text: object, *, context: str) -> str:
        return normalize_text(text)

    def close(self) -> None:
        return None


class ConservativeEvidenceTextCleaner(EvidenceTextCleaner):
    OCR_REPLACEMENTS = (
        (r"\bDemucratic\b", "Democratic"),
        (r"\bDEMOCRA TIC\b", "DEMOCRATIC"),
        (r"\bPr adeshiya\b", "Pradeshiya"),
        (r"\bPradeshiye\s*_\s*Sabha\b", "Pradeshiya Sabha"),
        (r"\bSsbha\b", "Sabha"),
        (r"\bSabbs\b", "Sabha"),
        (r"\bOsdcers\b", "Officers"),
        (r"\bservanis\b", "servants"),
        (r"\bservents\b", "servants"),
        (r"\bservanie\b", "servants"),
        (r"\bEect\b", "Effect"),
        (r"\biecal avtihority\b", "local authority"),
        (r"\bto ke\b", "to be"),
        (r"\btoe be\b", "to be"),
        (r"\bannyally\b", "annually"),
        (r"\byer\b", "year"),
        (r"\bPradeshiya Sabhaand\b", "Pradeshiya Sabha and"),
        (r"\bS EC\.", "SEC."),
        (r"\bSec \.", "Sec."),
        (r"\bPart I : Sec \.", "PART I : SEC."),
    )

    def clean(self, text: object, *, context: str) -> str:
        value = normalize_text(text)
        value = self.remove_garbled_parallel_header(value)
        value = self.remove_inline_ocr_header_noise(value)
        value = self.remove_repeated_page_marker(value)
        for pattern, replacement in self.OCR_REPLACEMENTS:
            value = re.sub(pattern, replacement, value)
        value = re.sub(r"\s+([,.;:])", r"\1", value)
        value = re.sub(r"([A-Za-z])\s+([-/])\s+([A-Za-z])", r"\1\2\3", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    @staticmethod
    def remove_garbled_parallel_header(value: str) -> str:
        upper_markers = ("PART I", "PART IV", "GAZETTE EXTRAORDINARY")
        first_marker_positions = [value.find(marker) for marker in upper_markers if value.find(marker) >= 0]
        if not first_marker_positions:
            return value
        first_marker = min(first_marker_positions)
        prefix = value[:first_marker]
        if first_marker <= 260 and re.search(r"(\^|%|fldgi|w;s|jeks|YS%|Y%S|fPoh|ckrcfha|w;s)", prefix):
            return value[first_marker:].lstrip(" -:;")
        return value

    @staticmethod
    def remove_repeated_page_marker(value: str) -> str:
        return re.sub(r"^\s*\d+[Aa]\s*(?=PART|This Gazette|MUNICIPAL|PROVINCIAL|The Gazette)", "", value)

    @staticmethod
    def remove_inline_ocr_header_noise(value: str) -> str:
        value = re.sub(r"\bY[%?]S\s*,?xld\s+m[%?]cd;dka;[%?]sl\s+iudcjd[?§]?\s+ckrcfha\s*\.?ei[?Ü]?\s*m;[%?]h\b", "", value)
        value = re.sub(r"\bw;s\s+\?fYI\s+wxl\s+[^.]{0,90}?(?=\bNo\.\s*\d)", "", value)
        return re.sub(r"\s{2,}", " ", value).strip()


class CachedAzureEvidenceTextCleaner(EvidenceTextCleaner):
    def __init__(
        self,
        *,
        cache_path: Path,
        account_name: str,
        deployment_name: str,
        chat_completions_url: str,
        api_version: str,
        clean_input_chars: int,
    ) -> None:
        from sl_legal_rag.llm import AzureChatClient, AzureChatConfig

        api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("AZURE_OPENAI_API_KEY is required for --clean-evidence-text")
        if not chat_completions_url:
            if not account_name or not deployment_name:
                raise RuntimeError(
                    "--clean-evidence-text requires AZURE_OPENAI_CHAT_COMPLETIONS_URL or account/deployment settings"
                )
            chat_completions_url = (
                f"https://{account_name}.cognitiveservices.azure.com/openai/deployments/"
                f"{deployment_name}/chat/completions?api-version={api_version}"
            )
        self.client = AzureChatClient(
            AzureChatConfig(
                account_name=account_name,
                deployment_name=deployment_name,
                chat_completions_url=chat_completions_url,
                api_key=api_key,
                api_version=api_version,
            )
        )
        self.cache_path = cache_path
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.clean_input_chars = clean_input_chars
        self.cache: dict[str, dict[str, str]] = {}
        if cache_path.exists():
            raw_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(raw_cache, dict):
                self.cache = {str(key): dict(value) for key, value in raw_cache.items() if isinstance(value, dict)}

    def cache_key(self, text: str, *, context: str) -> str:
        digest = hashlib.sha256(f"{context}\n{text}".encode("utf-8")).hexdigest()
        return digest

    def clean(self, text: object, *, context: str) -> str:
        source = normalize_text(text)
        if not source:
            return ""
        key = self.cache_key(source, context=context)
        cached = self.cache.get(key)
        if cached and cached.get("cleaned_text"):
            cleaned = ConservativeEvidenceTextCleaner().clean(cached["cleaned_text"], context=context)
            cached["cleaned_text"] = cleaned
            return cleaned
        cleaned = self.clean_full_text_with_llm(source, context=context)
        self.cache[key] = {
            "context": context,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "cleaned_text": cleaned,
        }
        return cleaned

    def clean_full_text_with_llm(self, text: str, *, context: str) -> str:
        cleaned_segments: list[str] = []
        for index, segment in enumerate(self.split_text_for_cleaning(text), start=1):
            segment_context = context if len(text) <= self.clean_input_chars else f"{context}: segment {index}"
            cleaned = self.clean_with_llm(segment, context=segment_context)
            cleaned = safe_cleaned_text(segment, cleaned)
            cleaned = ConservativeEvidenceTextCleaner().clean(cleaned, context=segment_context)
            cleaned_segments.append(cleaned)
        return normalize_text(" ".join(cleaned_segments))

    def split_text_for_cleaning(self, text: str) -> list[str]:
        if len(text) <= self.clean_input_chars:
            return [text]
        segments: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= self.clean_input_chars:
                segments.append(remaining)
                break
            window = remaining[: self.clean_input_chars]
            split_at = max(window.rfind(". "), window.rfind("; "), window.rfind(": "), window.rfind(") "))
            if split_at < max(400, int(self.clean_input_chars * 0.55)):
                split_at = self.clean_input_chars
            else:
                split_at += 1
            segments.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()
        return [segment for segment in segments if segment]

    def clean_with_llm(self, text: str, *, context: str) -> str:
        system = (
            "You clean OCR snippets for Sri Lankan legal evidence reports. "
            "Do not add facts, infer missing law, summarize, translate, or change legal meaning. "
            "Only remove obvious OCR garbage, duplicate garbled headers, broken line artifacts, and fix spacing/punctuation. "
            "If an English Gazette header appears next to unreadable romanized/non-English OCR noise, keep the English header and remove the unreadable duplicate. "
            "Return JSON only."
        )
        user = {
            "task": "Clean this evidence snippet for display in a PDF report without adding or omitting legal substance.",
            "context": context,
            "input_text": text,
            "output_schema": {"cleaned_text": "string"},
        }
        response = self.client.complete_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            max_completion_tokens=1800,
        )
        return str(response.get("cleaned_text") or "")

    def close(self) -> None:
        self.cache_path.write_text(json.dumps(self.cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def palette_for_type(document_type: str) -> DocumentPalette:
    lower = document_type.lower()
    if "constitution" in lower or "core legislation" in lower:
        return PALETTES["constitution"]
    if lower == "act" or "ordinance" in lower:
        return PALETTES["act"]
    if "bill" in lower:
        return PALETTES["bill"]
    if "gazette" in lower:
        return PALETTES["gazette"]
    if "supreme court" in lower:
        return PALETTES["supreme_court"]
    if "court of appeal" in lower:
        return PALETTES["court_of_appeal"]
    if "law report" in lower or "case digest" in lower:
        return PALETTES["law_report"]
    return PALETTES["other"]


def read_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{path} must contain a non-empty cases array")
    return payload


def normalize_psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def enrich_report_with_full_chunk_text(report: dict[str, Any], *, dsn: str) -> int:
    chunk_ids: list[str] = []
    chunk_refs: dict[str, list[dict[str, Any]]] = {}
    for case in report.get("cases", []):
        for document in case.get("top_documents", []):
            for chunk in document_evidence_chunks(document):
                chunk_id = str(chunk.get("chunk_id") or "")
                if chunk_id and not chunk.get("chunk_text"):
                    chunk_ids.append(chunk_id)
                    chunk_refs.setdefault(chunk_id, []).append(chunk)
    chunk_ids = sorted(set(chunk_ids))
    if not chunk_ids:
        return 0
    import psycopg

    with psycopg.connect(normalize_psycopg_dsn(dsn)) as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT chunk_id, chunk_text
            FROM retrieval_chunks
            WHERE chunk_id = ANY(%(chunk_ids)s)
            """,
            {"chunk_ids": chunk_ids},
        )
        rows = cursor.fetchall()
    updated = 0
    for chunk_id, chunk_text in rows:
        for chunk in chunk_refs.get(str(chunk_id), []):
            chunk["chunk_text"] = str(chunk_text or "")
            updated += 1
    return updated


def canonical_document_key(document: dict[str, Any]) -> str:
    for field in ("document_id", "local_path", "source_url"):
        value = normalize_text(document.get(field))
        if value:
            return f"{field}:{value.lower()}"
    title = clean_metadata_text(document.get("title")).lower()
    document_type = normalize_text(document.get("document_type")).lower()
    source_id = normalize_text(document.get("source_id")).lower()
    year = normalize_text(document.get("year")).lower()
    return f"fallback:{title}|{document_type}|{source_id}|{year}"


def document_evidence_chunks(document: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_chunk in document.get("evidence_chunks") or []:
        if not isinstance(raw_chunk, dict):
            continue
        chunk_id = str(raw_chunk.get("chunk_id") or "")
        dedupe_key = chunk_id or normalize_text(raw_chunk.get("excerpt") or raw_chunk.get("chunk_text"))[:240]
        if dedupe_key and dedupe_key in seen:
            continue
        if dedupe_key:
            seen.add(dedupe_key)
        chunks.append(raw_chunk)
    best_chunk = document.get("best_full_text_chunk")
    if isinstance(best_chunk, dict):
        chunk_id = str(best_chunk.get("chunk_id") or "")
        dedupe_key = chunk_id or normalize_text(best_chunk.get("excerpt") or best_chunk.get("chunk_text"))[:240]
        if dedupe_key and dedupe_key not in seen:
            chunks.insert(0, best_chunk)
    return chunks


def merge_duplicate_document(target: dict[str, Any], duplicate: dict[str, Any]) -> None:
    target["relevance_score"] = max(float(target.get("relevance_score") or 0), float(duplicate.get("relevance_score") or 0))
    target["rank"] = min(int(target.get("rank") or 10**9), int(duplicate.get("rank") or 10**9))
    ranks = list(target.get("combined_from_ranks") or [target["rank"]])
    duplicate_rank = duplicate.get("rank")
    if duplicate_rank is not None and duplicate_rank not in ranks:
        ranks.append(duplicate_rank)
    target["combined_from_ranks"] = sorted(ranks)
    merged_chunks = document_evidence_chunks(target)
    seen = {str(chunk.get("chunk_id") or "") for chunk in merged_chunks if chunk.get("chunk_id")}
    for chunk in document_evidence_chunks(duplicate):
        chunk_id = str(chunk.get("chunk_id") or "")
        if chunk_id and chunk_id in seen:
            continue
        if chunk_id:
            seen.add(chunk_id)
        merged_chunks.append(chunk)
    merged_chunks.sort(key=lambda chunk: float(chunk.get("chunk_score") or 0), reverse=True)
    target["evidence_chunks"] = merged_chunks
    if merged_chunks:
        target["best_full_text_chunk"] = merged_chunks[0]
    breakdown = dict(target.get("scoring_breakdown") or {})
    breakdown["evidence_chunk_count"] = len(merged_chunks)
    target["scoring_breakdown"] = breakdown


def distinct_case_documents(case: dict[str, Any], *, top_documents: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for document in case.get("top_documents", []):
        if not isinstance(document, dict):
            continue
        key = canonical_document_key(document)
        if key not in merged:
            copied = dict(document)
            copied["evidence_chunks"] = document_evidence_chunks(copied)
            if copied["evidence_chunks"]:
                copied["best_full_text_chunk"] = copied["evidence_chunks"][0]
            copied["combined_from_ranks"] = [copied.get("rank")] if copied.get("rank") is not None else []
            merged[key] = copied
            ordered_keys.append(key)
        else:
            merge_duplicate_document(merged[key], document)
    distinct = [merged[key] for key in ordered_keys]
    distinct.sort(key=lambda item: int(item.get("rank") or 10**9))
    distinct = distinct[:top_documents]
    for index, document in enumerate(distinct, start=1):
        document["rank"] = index
    return distinct


def grouped_documents(case: dict[str, Any], *, top_documents: int) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for document in distinct_case_documents(case, top_documents=top_documents):
        document_type = str(document.get("document_type") or "Other")
        if document_type not in groups:
            groups[document_type] = []
            order.append(document_type)
        groups[document_type].append(document)
    return [(document_type, groups[document_type]) for document_type in order]


def document_excerpt(
    document: dict[str, Any],
    *,
    chunk_chars: int,
    cleaner: EvidenceTextCleaner,
    context: str,
) -> str:
    chunk = document.get("best_full_text_chunk") or {}
    if chunk.get("chunk_text"):
        cleaned = cleaner.clean(chunk["chunk_text"], context=f"{context}: full-text chunk")
        return normalize_text(cleaned)
    excerpt = chunk.get("excerpt") or document.get("summary_search_excerpt") or ""
    cleaned = cleaner.clean(excerpt, context=f"{context}: full-text chunk")
    return normalize_text(cleaned, max_chars=chunk_chars)


def chunk_heading(chunk: dict[str, Any], *, index: int) -> str:
    parts = [f"Chunk {index}"]
    if chunk.get("page_start") or chunk.get("page_end"):
        parts.append(f"pages {chunk.get('page_start') or '?'}-{chunk.get('page_end') or chunk.get('page_start') or '?'}")
    if chunk.get("chunk_score") is not None:
        try:
            parts.append(f"score {float(chunk.get('chunk_score')):.3f}")
        except (TypeError, ValueError):
            parts.append(f"score {normalize_text(chunk.get('chunk_score'))}")
    return " -- ".join(parts)


def chunk_summary(
    chunk: dict[str, Any],
    *,
    query: object,
    max_chars: int,
    cleaner: EvidenceTextCleaner,
    context: str,
) -> str:
    source_text = chunk.get("chunk_text") or chunk.get("excerpt") or ""
    summary = extractive_summary(source_text, query=query, max_chars=max_chars)
    cleaned = cleaner.clean(summary, context=context)
    return normalize_text(cleaned)


def rendered_chunk_summaries(
    document: dict[str, Any],
    *,
    query: object,
    chunk_chars: int,
    cleaner: EvidenceTextCleaner,
    context: str,
) -> str:
    chunks = document_evidence_chunks(document)
    if not chunks:
        fallback = document_excerpt(document, chunk_chars=chunk_chars, cleaner=cleaner, context=context)
        return latex_escape(fallback)
    rendered: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        summary = chunk_summary(
            chunk,
            query=query,
            max_chars=chunk_chars,
            cleaner=cleaner,
            context=f"{context}: {chunk_heading(chunk, index=index)}",
        )
        rendered.append(
            textwrap.dedent(
                rf"""
                \textbf{{{latex_escape(chunk_heading(chunk, index=index))}}}\\
                {latex_escape(summary)}
                """
            ).strip()
        )
    return "\n\n\\medskip\n".join(rendered)


def evidence_box(
    document: dict[str, Any],
    *,
    chunk_chars: int,
    cleaner: EvidenceTextCleaner,
    case_id: str,
    query: object,
    include_summary_abstract: bool,
) -> str:
    document_type = str(document.get("document_type") or "Other")
    palette = palette_for_type(document_type)
    title = clean_metadata_text(document.get("title"))
    year = document.get("year") or "Unknown"
    score = document.get("relevance_score")
    score_text = f"{float(score):.2f}" if isinstance(score, (float, int)) else normalize_text(score or "0")
    source = document.get("source_id") or "Unknown source"
    context = f"{case_id} / {document.get('document_id')} / rank {document.get('rank')}"
    chunk_count = len(document_evidence_chunks(document))
    excerpt = rendered_chunk_summaries(
        document,
        query=query,
        chunk_chars=chunk_chars,
        cleaner=cleaner,
        context=context,
    )
    summary_section = ""
    if include_summary_abstract:
        summary_excerpt = normalize_text(
            cleaner.clean(document.get("summary_search_excerpt"), context=f"{context}: summary-search abstract"),
            max_chars=500,
        )
        summary_section = textwrap.dedent(
            rf"""

            \medskip
            \textbf{{Summary-search abstract}}\\
            {latex_escape(summary_excerpt)}
            """
        ).rstrip()
    return textwrap.dedent(
        rf"""
        \begin{{tcolorbox}}[
          enhanced,
          breakable,
          colback={palette.back},
          colframe={palette.frame},
          colbacktitle={palette.title},
          coltitle=white,
          fonttitle=\bfseries,
          title={{Rank {document.get('rank')} -- {latex_escape(document_type)}}}
        ]
        \textbf{{Title:}} {latex_escape(title)}\\
        \textbf{{Year:}} {latex_escape(year)}\\
        \textbf{{Final relevance score:}} {latex_escape(score_text)}\\
        \textbf{{Source:}} {latex_escape(source)}\\
        \textbf{{Evidence chunks combined:}} {latex_escape(chunk_count)}

        \medskip
        \textbf{{Relevant chunk summaries}}\\
        {excerpt}
        {summary_section}
        \end{{tcolorbox}}
        """
    ).strip()


def summary_box(case: dict[str, Any], *, top_documents: int) -> str:
    metrics = case.get("metrics") or {}
    top_docs = distinct_case_documents(case, top_documents=top_documents)
    type_counts: dict[str, int] = {}
    for document in top_docs:
        document_type = str(document.get("document_type") or "Other")
        type_counts[document_type] = type_counts.get(document_type, 0) + 1
    types_line = ", ".join(f"{count} {doc_type}" for doc_type, count in sorted(type_counts.items())) or "No documents returned"
    top_titles = "; ".join(normalize_text(doc.get("title"), max_chars=90) for doc in top_docs[:5])
    failures = "; ".join(case.get("failures") or []) or "No retrieval gate failures for this case."
    return textwrap.dedent(
        rf"""
        \begin{{tcolorbox}}[
          enhanced,
          breakable,
          colback=SummaryBack,
          colframe=SummaryFrame,
          colbacktitle=SummaryTitle,
          coltitle=white,
          fonttitle=\bfseries,
          title={{Summary}}
        ]
        Stage 1 returned \textbf{{{latex_escape(case.get('stage1_candidate_count', 0))}}} broad candidates.
        The expected-authority recall was \textbf{{{latex_escape(metrics.get('stage1_expected_recall', 'n/a'))}}} in stage 1
        and \textbf{{{latex_escape(metrics.get('top_k_expected_recall', 'n/a'))}}} in the final top {latex_escape(top_documents)}.

        \medskip
        The final set shown in this report contains: {latex_escape(types_line)}.

        \medskip
        Highest-ranked materials: {latex_escape(top_titles)}

        \medskip
        Retrieval status: {latex_escape(failures)}
        \end{{tcolorbox}}
        """
    ).strip()


def case_overview_box(case: dict[str, Any], report: dict[str, Any]) -> str:
    metrics = case.get("metrics") or {}
    return textwrap.dedent(
        rf"""
        \begin{{tcolorbox}}[
          enhanced,
          breakable,
          colback=CaseBack,
          colframe=CaseFrame,
          colbacktitle=CaseTitle,
          coltitle=black,
          fonttitle=\bfseries,
          title={{Case}}
        ]
        \textbf{{Case title:}} {latex_escape(case.get('title'))}\\
        \textbf{{Case ID:}} \texttt{{{latex_escape(case.get('case_id'))}}}\\
        \textbf{{Status:}} {latex_escape(case.get('status'))}\\
        \textbf{{Elapsed:}} {latex_escape(case.get('elapsed_ms'))} ms\\
        \textbf{{Report:}} \texttt{{{latex_escape(report.get('fixture_path'))}}}

        \medskip
        \textbf{{Facts}}\\
        {latex_escape(case.get('case_facts'))}

        \medskip
        \textbf{{Retrieval query}}\\
        {latex_escape(case.get('query'))}

        \medskip
        \textbf{{Search gates}}\\
        Stage 1 candidates: {latex_escape(case.get('stage1_candidate_count'))}.
        Expected documents resolved: {latex_escape(metrics.get('expected_count'))}.
        Stage 1 expected recall: {latex_escape(metrics.get('stage1_expected_recall'))}.
        Final top-K expected recall: {latex_escape(metrics.get('top_k_expected_recall'))}.
        \end{{tcolorbox}}
        """
    ).strip()


def latex_preamble() -> str:
    return r"""
\documentclass[11pt]{article}
\usepackage[a4paper,margin=0.65in]{geometry}
\usepackage[most]{tcolorbox}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{tabularx}
\usepackage{array}
\usepackage{titlesec}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\hypersetup{colorlinks=true,linkcolor=blue,urlcolor=blue}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.45em}
\setlist{nosep,leftmargin=1.5em}
\titleformat{\section}{\large\bfseries}{\thesection}{0.5em}{}
\definecolor{CaseFrame}{HTML}{6B7280}
\definecolor{CaseBack}{HTML}{F3F4F6}
\definecolor{CaseTitle}{HTML}{E5E7EB}
\definecolor{SummaryFrame}{HTML}{1D4ED8}
\definecolor{SummaryBack}{HTML}{EFF6FF}
\definecolor{SummaryTitle}{HTML}{2563EB}
\definecolor{ActFrame}{HTML}{15803D}
\definecolor{ActBack}{HTML}{F0FDF4}
\definecolor{ActTitle}{HTML}{16A34A}
\definecolor{BillFrame}{HTML}{0E7490}
\definecolor{BillBack}{HTML}{ECFEFF}
\definecolor{BillTitle}{HTML}{0891B2}
\definecolor{GazetteFrame}{HTML}{B45309}
\definecolor{GazetteBack}{HTML}{FFFBEB}
\definecolor{GazetteTitle}{HTML}{D97706}
\definecolor{SupremeFrame}{HTML}{6D28D9}
\definecolor{SupremeBack}{HTML}{F5F3FF}
\definecolor{SupremeTitle}{HTML}{7C3AED}
\definecolor{AppealFrame}{HTML}{0369A1}
\definecolor{AppealBack}{HTML}{F0F9FF}
\definecolor{AppealTitle}{HTML}{0284C7}
\definecolor{ReportFrame}{HTML}{BE123C}
\definecolor{ReportBack}{HTML}{FFF1F2}
\definecolor{ReportTitle}{HTML}{E11D48}
\definecolor{ConstitutionFrame}{HTML}{4338CA}
\definecolor{ConstitutionBack}{HTML}{EEF2FF}
\definecolor{ConstitutionTitle}{HTML}{4F46E5}
\definecolor{OtherFrame}{HTML}{475569}
\definecolor{OtherBack}{HTML}{F8FAFC}
\definecolor{OtherTitle}{HTML}{64748B}
\tcbset{
  reportbox/.style={
    enhanced,
    breakable,
    boxrule=0.7pt,
    arc=2mm,
    left=2mm,
    right=2mm,
    top=1.5mm,
    bottom=1.5mm
  }
}
""".strip()


def render_case_tex(
    report: dict[str, Any],
    case: dict[str, Any],
    *,
    top_documents: int,
    chunk_chars: int,
    cleaner: EvidenceTextCleaner | None = None,
    include_summary_abstract: bool = False,
) -> str:
    cleaner = cleaner or EvidenceTextCleaner()
    pieces = [
        latex_preamble(),
        rf"\title{{Sri Lankan Legal AI Retrieval Evidence Report}}",
        rf"\author{{Generated from two-stage retrieval results}}",
        rf"\date{{{latex_escape(time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))}}}",
        r"\begin{document}",
        r"\maketitle",
        case_overview_box(case, report),
        r"\newpage",
        r"\section*{Evidence Documents}",
    ]
    for document_type, documents in grouped_documents(case, top_documents=top_documents):
        pieces.append(rf"\subsection*{{{latex_escape(document_type)} ({len(documents)})}}")
        for document in documents:
            pieces.append(
                evidence_box(
                    document,
                    chunk_chars=chunk_chars,
                    cleaner=cleaner,
                    case_id=str(case.get("case_id") or ""),
                    query=case.get("query") or case.get("case_facts") or "",
                    include_summary_abstract=include_summary_abstract,
                )
            )
    pieces.extend([summary_box(case, top_documents=top_documents), r"\end{document}", ""])
    return "\n\n".join(pieces)


def compile_tex(tex_path: Path, *, compiler: str) -> Path:
    if compiler == "auto":
        if shutil.which("tectonic"):
            compiler = "tectonic"
        elif shutil.which("latexmk"):
            compiler = "latexmk"
        else:
            compiler = "pdflatex"
    if compiler == "tectonic":
        if not shutil.which("tectonic"):
            raise RuntimeError("tectonic is not installed")
        command = ["tectonic", "-X", "compile", "--outdir", str(tex_path.parent), "--outfmt", "pdf", str(tex_path.name)]
        subprocess.run(command, cwd=tex_path.parent, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    elif compiler == "latexmk":
        if not shutil.which("latexmk"):
            raise RuntimeError("latexmk is not installed")
        command = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", str(tex_path.name)]
        subprocess.run(command, cwd=tex_path.parent, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    else:
        if not shutil.which("pdflatex"):
            raise RuntimeError("pdflatex is not installed")
        command = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", str(tex_path.name)]
        for _ in range(2):
            subprocess.run(command, cwd=tex_path.parent, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"expected PDF was not produced: {pdf_path}")
    return pdf_path


def generate_reports(
    report: dict[str, Any],
    output_dir: Path,
    *,
    top_documents: int,
    chunk_chars: int,
    compile_pdf: bool,
    compiler: str,
    cleaner: EvidenceTextCleaner | None = None,
    case_ids: set[str] | None = None,
    include_summary_abstract: bool = False,
) -> list[dict[str, Any]]:
    cleaner = cleaner or EvidenceTextCleaner()
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, Any]] = []
    for index, case in enumerate(report["cases"], start=1):
        if case_ids and str(case.get("case_id")) not in case_ids:
            continue
        stem = f"{index:02d}_{slugify(str(case.get('case_id')))}"
        tex_path = output_dir / f"{stem}.tex"
        tex_path.write_text(
            render_case_tex(
                report,
                case,
                top_documents=top_documents,
                chunk_chars=chunk_chars,
                cleaner=cleaner,
                include_summary_abstract=include_summary_abstract,
            ),
            encoding="utf-8",
        )
        item = {
            "case_id": case.get("case_id"),
            "title": case.get("title"),
            "tex_path": str(tex_path),
            "pdf_path": None,
            "status": "tex_written",
        }
        if compile_pdf:
            pdf_path = compile_tex(tex_path, compiler=compiler)
            item["pdf_path"] = str(pdf_path)
            item["status"] = "pdf_compiled"
        generated.append(item)
    return generated


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report_path = resolve_project_path(args.report_json)
    output_dir = resolve_project_path(args.output_dir)
    report = read_report(report_path)
    enriched_chunks = 0
    if args.fetch_full_chunk_text:
        enriched_chunks = enrich_report_with_full_chunk_text(report, dsn=args.dsn)
    cache_path = resolve_project_path(args.clean_cache) if args.clean_cache else output_dir / "llm_clean_text_cache.json"
    cleaner: EvidenceTextCleaner = EvidenceTextCleaner()
    if args.clean_evidence_text:
        cleaner = CachedAzureEvidenceTextCleaner(
            cache_path=cache_path,
            account_name=args.azure_account_name,
            deployment_name=args.azure_deployment_name,
            chat_completions_url=args.azure_chat_completions_url,
            api_version=args.azure_api_version,
            clean_input_chars=args.clean_input_chars,
        )
    elif args.conservative_clean_evidence_text:
        cleaner = ConservativeEvidenceTextCleaner()
    try:
        generated = generate_reports(
            report,
            output_dir,
            top_documents=args.top_documents,
            chunk_chars=args.chunk_chars,
            compile_pdf=args.compile,
            compiler=args.compiler,
            cleaner=cleaner,
            case_ids=set(args.case_id) if args.case_id else None,
            include_summary_abstract=args.include_summary_abstract,
        )
    finally:
        cleaner.close()
    manifest_path = output_dir / "case_report_manifest.json"
    manifest = {
        "source_report": str(report_path),
        "output_dir": str(output_dir),
        "top_documents": args.top_documents,
        "case_ids": args.case_id,
        "chunk_chars": args.chunk_chars,
        "include_summary_abstract": args.include_summary_abstract,
        "full_chunk_text": {
            "fetched_from_postgres": args.fetch_full_chunk_text,
            "enriched_chunks": enriched_chunks,
        },
        "text_cleaning": {
            "enabled": args.clean_evidence_text or args.conservative_clean_evidence_text,
            "cache_path": str(cache_path) if args.clean_evidence_text else None,
            "provider": "azure_openai" if args.clean_evidence_text else "conservative" if args.conservative_clean_evidence_text else "none",
        },
        "compiled": args.compile,
        "generated_count": len(generated),
        "reports": generated,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"manifest_path": str(manifest_path), "generated_count": len(generated)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
