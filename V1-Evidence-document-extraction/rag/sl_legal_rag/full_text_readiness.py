from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


READY_EXTRACTION_STATUSES = {"text_extracted"}
OCR_PENDING_EXTRACTION_STATUSES = {"text_empty_needs_ocr"}
TEXT_EXTRACTED_STATUSES = READY_EXTRACTION_STATUSES | OCR_PENDING_EXTRACTION_STATUSES
OCR_COMPLETE_PREFIX = "ocr_completed"


@dataclass(frozen=True)
class SourceTextReadiness:
    source_id: str
    downloaded: int = 0
    full_text_ready: int = 0
    extraction_pending: int = 0
    ocr_pending: int = 0
    extraction_failed: int = 0
    blocked_non_pdf: int = 0


@dataclass(frozen=True)
class FullTextReadinessReport:
    total_manifest_rows: int
    downloaded_documents: int
    downloaded_pdfs: int
    downloaded_non_pdfs: int
    text_extracted_documents: int
    text_empty_needs_ocr_documents: int
    ocr_completed_documents: int
    full_text_ready_documents: int
    extraction_pending_documents: int
    ocr_pending_documents: int
    extraction_failed_documents: int
    package_extracted_documents: int
    blocked_non_pdf_documents: int
    source_summaries: list[SourceTextReadiness] = field(default_factory=list)

    @property
    def remaining_for_full_text(self) -> int:
        return max(0, self.downloaded_documents - self.full_text_ready_documents)

    @property
    def full_text_ready_ratio(self) -> float:
        if self.downloaded_documents == 0:
            return 0.0
        return self.full_text_ready_documents / self.downloaded_documents

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["remaining_for_full_text"] = self.remaining_for_full_text
        payload["full_text_ready_ratio"] = round(self.full_text_ready_ratio, 6)
        return payload


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_ocr_rows(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv_rows(path)
    return {row.get("document_id", ""): row for row in rows if row.get("document_id")}


def write_report_json(path: Path, report: FullTextReadinessReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_downloaded(row: dict[str, str]) -> bool:
    return row.get("acquisition_status") == "downloaded"


def is_pdf(row: dict[str, str]) -> bool:
    return row.get("local_path", "").lower().endswith(".pdf")


def parse_bool(value: str | None) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def parse_float(value: str | None) -> float | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def ocr_completed(ocr_row: dict[str, str] | None) -> bool:
    if not ocr_row:
        return False
    status = ocr_row.get("ocr_status", "")
    if not status.startswith(OCR_COMPLETE_PREFIX):
        return False
    try:
        return int(ocr_row.get("char_count") or "0") > 0
    except ValueError:
        return False


def row_has_ready_text(
    row: dict[str, str],
    ocr_row: dict[str, str] | None,
    *,
    minimum_text_quality: float,
) -> bool:
    extraction_status = row.get("extraction_status", "")
    ocr_required = parse_bool(row.get("ocr_required"))
    text_quality = parse_float(row.get("text_quality_score"))
    if ocr_completed(ocr_row):
        return True
    if extraction_status not in READY_EXTRACTION_STATUSES:
        return False
    if ocr_required is True:
        return False
    if text_quality is None:
        return True
    return text_quality >= minimum_text_quality


def row_needs_ocr(row: dict[str, str], ocr_row: dict[str, str] | None) -> bool:
    if ocr_completed(ocr_row):
        return False
    extraction_status = row.get("extraction_status", "")
    return extraction_status in OCR_PENDING_EXTRACTION_STATUSES or parse_bool(row.get("ocr_required")) is True


def build_full_text_readiness_report(
    manifest_rows: Iterable[dict[str, str]],
    ocr_rows_by_document_id: dict[str, dict[str, str]],
    *,
    minimum_text_quality: float = 0.60,
) -> FullTextReadinessReport:
    rows = list(manifest_rows)
    counts: Counter[str] = Counter()
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)

    def inc(row: dict[str, str], key: str) -> None:
        counts[key] += 1
        source_counts[row.get("source_id", "")][key] += 1

    for row in rows:
        if not is_downloaded(row):
            continue
        inc(row, "downloaded_documents")
        if is_pdf(row):
            inc(row, "downloaded_pdfs")
        else:
            inc(row, "downloaded_non_pdfs")
            inc(row, "blocked_non_pdf_documents")

        extraction_status = row.get("extraction_status", "")
        ocr_row = ocr_rows_by_document_id.get(row.get("document_id", ""))

        if extraction_status == "text_extracted":
            inc(row, "text_extracted_documents")
        elif extraction_status == "text_empty_needs_ocr":
            inc(row, "text_empty_needs_ocr_documents")
        elif extraction_status == "package_extracted":
            inc(row, "package_extracted_documents")
        elif "failed" in extraction_status:
            inc(row, "extraction_failed_documents")
        else:
            inc(row, "extraction_pending_documents")

        if ocr_completed(ocr_row):
            inc(row, "ocr_completed_documents")
        if row_needs_ocr(row, ocr_row):
            inc(row, "ocr_pending_documents")
        if row_has_ready_text(row, ocr_row, minimum_text_quality=minimum_text_quality):
            inc(row, "full_text_ready_documents")

    summaries = [
        SourceTextReadiness(
            source_id=source_id,
            downloaded=counter["downloaded_documents"],
            full_text_ready=counter["full_text_ready_documents"],
            extraction_pending=counter["extraction_pending_documents"],
            ocr_pending=counter["ocr_pending_documents"],
            extraction_failed=counter["extraction_failed_documents"],
            blocked_non_pdf=counter["blocked_non_pdf_documents"],
        )
        for source_id, counter in sorted(
            source_counts.items(),
            key=lambda item: (-item[1]["downloaded_documents"], item[0]),
        )
    ]

    return FullTextReadinessReport(
        total_manifest_rows=len(rows),
        downloaded_documents=counts["downloaded_documents"],
        downloaded_pdfs=counts["downloaded_pdfs"],
        downloaded_non_pdfs=counts["downloaded_non_pdfs"],
        text_extracted_documents=counts["text_extracted_documents"],
        text_empty_needs_ocr_documents=counts["text_empty_needs_ocr_documents"],
        ocr_completed_documents=counts["ocr_completed_documents"],
        full_text_ready_documents=counts["full_text_ready_documents"],
        extraction_pending_documents=counts["extraction_pending_documents"],
        ocr_pending_documents=counts["ocr_pending_documents"],
        extraction_failed_documents=counts["extraction_failed_documents"],
        package_extracted_documents=counts["package_extracted_documents"],
        blocked_non_pdf_documents=counts["blocked_non_pdf_documents"],
        source_summaries=summaries,
    )
