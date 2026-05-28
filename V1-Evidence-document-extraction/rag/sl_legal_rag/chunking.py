from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]


PRIORITY_SOURCE_IDS = {
    "PARL_ACTS",
    "PARL_GOV_BILLS",
    "PARL_SC_DECISIONS_ON_BILLS",
    "PARL_HANSARD_DAILY",
    "PARL_HANSARD_VOLUMES",
    "PARL_ORDER_PAPERS",
    "PARL_ORDER_BOOKS",
    "PARL_ORDER_OF_BUSINESS",
    "PARL_ADDENDUMS",
    "PARL_MINUTES",
    "PARL_PAPERS_PRESENTED",
    "PARL_COMMITTEE_REPORTS",
    "PARL_PROGRESS_REPORTS",
    "PARL_SPEAKER_PAPERS",
    "PARL_CONSULTATIVE_MONTHLY_REPORTS",
    "PARL_MINISTERIAL_CONSULTATIVE_REPORTS",
    "SUPREME_COURT",
    "SC_OFFICIAL",
    "COURT_OF_APPEAL",
    "CA_OFFICIAL",
    "LAW_REPORTS",
    "LANKALAW",
    "LANKALAW_NET",
    "ADMIN_PRACTICE",
    "CBSL_RULES_DIRECTIONS",
    "PROVINCIAL_SUBNATIONAL",
    "UVA_HEALTH_STATUTES",
    "UVA_PSC_LEGAL_PROVISIONS",
}


AUTHORITY_BY_TYPE = {
    "Constitution": 1,
    "Act": 2,
    "Consolidated Act": 2,
    "Bill": 8,
    "Government Bill": 8,
    "Supreme Court Judgment": 3,
    "Supreme Court": 3,
    "Court of Appeal Judgment": 4,
    "Court of Appeal": 4,
    "Law Report": 4,
    "Gazette": 5,
    "Extraordinary Gazette": 5,
    "Parliament Hansard": 6,
    "Administrative Practice Material": 6,
    "Provincial/Subnational Law": 6,
}


NOTE_PATH_RE = re.compile(r"(?P<key>ocr_pages_path|pages_path|ocr_text_path|text_path)=([^;]+)")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
WHITESPACE_RE = re.compile(r"[ \t]+")
PARA_SPLIT_RE = re.compile(r"\n{2,}")


@dataclass
class PageRecord:
    page_number: int
    text: str
    error: str = ""
    confidence: float | None = None
    extraction_method: str = "text"


@dataclass
class LegalChunk:
    chunk_id: str
    document_id: str
    source_id: str
    document_type: str
    title: str
    year: int | None
    number: str
    date: str
    language: str
    authority_level: int
    page_start: int | None
    page_end: int | None
    chunk_index: int
    chunk_text: str
    token_estimate: int
    citation: str
    source_url: str
    local_path: str
    text_hash: str
    quality_flags: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    text_version_id: str = ""
    text_origin: str = "source"
    source_language: str = ""
    translated_from_language: str = ""
    translation_review_status: str = ""

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(*parts: object) -> str:
    raw = "::".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def estimate_tokens(text: str) -> int:
    # Good enough for chunk budgeting before tokenizer-specific packing.
    return max(1, len(text.split()) * 4 // 3)


def normalize_text(text: str) -> str:
    text = CONTROL_CHAR_RE.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def parse_note_paths(notes: str) -> dict[str, str]:
    return {match.group("key"): match.group(2).strip() for match in NOTE_PATH_RE.finditer(notes or "")}


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_ocr_register(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["document_id"]: row for row in csv.DictReader(handle)}


def read_pages_jsonl(path: Path, extraction_method: str, confidence: float | None = None) -> list[PageRecord]:
    pages: list[PageRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            page_number = int(raw.get("page") or raw.get("page_number") or 0)
            pages.append(
                PageRecord(
                    page_number=page_number,
                    text=normalize_text(str(raw.get("text") or "")),
                    error=str(raw.get("error") or ""),
                    confidence=confidence,
                    extraction_method=extraction_method,
                )
            )
    return pages


def pages_for_manifest_row(row: dict[str, str], ocr_register: dict[str, dict[str, str]]) -> list[PageRecord]:
    document_id = row["document_id"]
    ocr_row = ocr_register.get(document_id)
    if ocr_row and ocr_row.get("ocr_pages_path"):
        path = PROJECT_ROOT / ocr_row["ocr_pages_path"]
        if path.exists() and ocr_row.get("ocr_status", "").startswith("ocr_completed"):
            confidence = None
            if ocr_row.get("mean_confidence"):
                try:
                    confidence = float(ocr_row["mean_confidence"])
                except ValueError:
                    confidence = None
            return read_pages_jsonl(path, extraction_method="ocr", confidence=confidence)

    paths = parse_note_paths(row.get("notes", ""))
    pages_path = paths.get("pages_path")
    if pages_path:
        path = PROJECT_ROOT / pages_path
        if path.exists():
            return read_pages_jsonl(path, extraction_method="text")

    return []


def infer_authority_level(row: dict[str, str]) -> int:
    document_type = row.get("document_type", "")
    if document_type in AUTHORITY_BY_TYPE:
        return AUTHORITY_BY_TYPE[document_type]
    source_id = row.get("source_id", "")
    if "SUPREME" in source_id:
        return 3
    if "COURT_OF_APPEAL" in source_id:
        return 4
    if "ACT" in source_id:
        return 2
    if "GAZETTE" in source_id:
        return 5
    if "HANSARD" in source_id:
        return 6
    return 8


def citation_for(row: dict[str, str], page_start: int | None, page_end: int | None) -> str:
    bits = [row.get("title") or row["document_id"]]
    if row.get("number") and row.get("year"):
        bits.append(f"No. {row['number']} of {row['year']}")
    elif row.get("year"):
        bits.append(str(row["year"]))
    if page_start and page_end and page_start != page_end:
        bits.append(f"pp. {page_start}-{page_end}")
    elif page_start:
        bits.append(f"p. {page_start}")
    return ", ".join(bits)


def split_page_to_paragraphs(page: PageRecord) -> list[str]:
    text = normalize_text(page.text)
    if not text:
        return []
    paragraphs = [normalize_text(part) for part in PARA_SPLIT_RE.split(text)]
    return [part for part in paragraphs if part]


def split_oversized_paragraph(paragraph: str, target_tokens: int) -> list[str]:
    if estimate_tokens(paragraph) <= target_tokens:
        return [paragraph]

    max_words = max(1, target_tokens * 3 // 4)
    words = paragraph.split()
    if len(words) > 1:
        return [" ".join(words[start : start + max_words]) for start in range(0, len(words), max_words)]

    # Some OCR outputs can contain a long run without whitespace. Keep those
    # retrievable by falling back to a conservative character window.
    max_chars = max(256, target_tokens * 4)
    return [paragraph[start : start + max_chars] for start in range(0, len(paragraph), max_chars)]


def chunk_pages(
    row: dict[str, str],
    pages: Iterable[PageRecord],
    *,
    target_tokens: int = 650,
    overlap_tokens: int = 80,
) -> Iterator[LegalChunk]:
    buffer: list[tuple[PageRecord, str]] = []
    buffer_tokens = 0
    chunk_index = 0
    authority_level = infer_authority_level(row)

    def emit() -> LegalChunk | None:
        nonlocal chunk_index
        if not buffer:
            return None
        text = "\n\n".join(part for _, part in buffer).strip()
        if not text:
            return None
        page_records = [page for page, _ in buffer]
        pages_in_chunk = [page.page_number for page in page_records if page.page_number > 0]
        page_start = min(pages_in_chunk) if pages_in_chunk else None
        page_end = max(pages_in_chunk) if pages_in_chunk else None
        quality_flags = quality_flags_for_chunk(page_records, text)
        text_origin = row.get("text_origin", "") or "source"
        translation_review_status = row.get("translation_review_status", "")
        if text_origin == "translation":
            quality_flags = sorted(set(quality_flags) | {"translated_text_fallback"})
            if translation_review_status != "lawyer_approved":
                quality_flags = sorted(set(quality_flags) | {"machine_translation_unreviewed"})
        if row.get("page_anchor_status") == "translation_full_text_no_page_map":
            quality_flags = sorted(set(quality_flags) | {"missing_page_anchor"})
        chunk_id = f"chunk_{row['document_id']}_{chunk_index:05d}_{stable_id(text)}"
        chunk = LegalChunk(
            chunk_id=chunk_id,
            document_id=row["document_id"],
            source_id=row.get("source_id", ""),
            document_type=row.get("document_type", ""),
            title=row.get("title", ""),
            year=int(row["year"]) if row.get("year", "").isdigit() else None,
            number=row.get("number", ""),
            date=row.get("date", ""),
            language=row.get("language", ""),
            authority_level=authority_level,
            page_start=page_start,
            page_end=page_end,
            chunk_index=chunk_index,
            chunk_text=text,
            token_estimate=estimate_tokens(text),
            citation=citation_for(row, page_start, page_end),
            source_url=row.get("source_url", ""),
            local_path=row.get("local_path", ""),
            text_hash=stable_hash(text),
            quality_flags=quality_flags,
            metadata={
                "source_document_id": row.get("source_document_id", ""),
                "legal_status": row.get("legal_status", ""),
                "extraction_status": row.get("extraction_status", ""),
                "quality_flags": quality_flags,
                "extraction_methods": sorted({page.extraction_method for page in page_records if page.extraction_method}),
                "text_version_id": row.get("text_version_id", ""),
                "text_origin": text_origin,
                "source_language": row.get("source_language", "") or row.get("language", ""),
                "translated_from_language": row.get("translated_from_language", ""),
                "translation_review_status": translation_review_status,
                "page_anchor_status": row.get("page_anchor_status", ""),
            },
            text_version_id=row.get("text_version_id", ""),
            text_origin=text_origin,
            source_language=row.get("source_language", "") or row.get("language", ""),
            translated_from_language=row.get("translated_from_language", ""),
            translation_review_status=translation_review_status,
        )
        chunk_index += 1
        return chunk

    for page in pages:
        for paragraph in split_page_to_paragraphs(page):
            for segment in split_oversized_paragraph(paragraph, target_tokens):
                paragraph_tokens = estimate_tokens(segment)
                if buffer and buffer_tokens + paragraph_tokens > target_tokens:
                    chunk = emit()
                    if chunk:
                        yield chunk
                    overlap: list[tuple[PageRecord, str]] = []
                    overlap_total = 0
                    for item_page, item_text in reversed(buffer):
                        item_tokens = estimate_tokens(item_text)
                        if overlap_total + item_tokens > overlap_tokens:
                            break
                        overlap.append((item_page, item_text))
                        overlap_total += item_tokens
                    buffer = list(reversed(overlap))
                    buffer_tokens = overlap_total
                buffer.append((page, segment))
                buffer_tokens += paragraph_tokens

                if buffer_tokens >= target_tokens:
                    chunk = emit()
                    if chunk:
                        yield chunk
                    buffer = []
                    buffer_tokens = 0

    chunk = emit()
    if chunk:
        yield chunk


def quality_flags_for_chunk(page_records: list[PageRecord], text: str) -> list[str]:
    flags: set[str] = set()
    if any(page.error for page in page_records):
        flags.add("page_extraction_error")
    if any(page.extraction_method == "ocr" for page in page_records):
        flags.add("ocr_text")
    if any(is_low_confidence_ocr_page(page) for page in page_records):
        flags.add("low_confidence_ocr")
    if len(text.strip()) < 80:
        flags.add("very_short_chunk_text")
    return sorted(flags)


def is_low_confidence_ocr_page(page: PageRecord) -> bool:
    if page.extraction_method != "ocr" or page.confidence is None:
        return False
    confidence = page.confidence * 100 if page.confidence <= 1 else page.confidence
    return confidence < 70
