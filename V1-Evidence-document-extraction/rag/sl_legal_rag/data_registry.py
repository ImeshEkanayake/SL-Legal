from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


REQUIRED_DOCUMENT_FIELDS = ("document_id", "source_id", "document_type", "title", "acquisition_status")
MISSING_ACQUISITION_STATUSES = {
    "download_failed",
    "metadata_extracted",
    "metadata_extracted_pdf_not_found",
    "licensed_purchase_required",
}
DOWNLOADED_ACQUISITION_STATUSES = {"downloaded"}


@dataclass(frozen=True)
class RegistryValidationIssue:
    row_number: int
    field: str
    message: str


@dataclass(frozen=True)
class RegistryValidationReport:
    row_count: int
    duplicate_document_ids: tuple[str, ...]
    issues: tuple[RegistryValidationIssue, ...]
    downloaded_count: int
    missing_count: int

    @property
    def valid(self) -> bool:
        return not self.duplicate_document_ids and not self.issues


def normalize_document_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "document_id": _clean(row.get("document_id")),
        "source_id": _clean(row.get("source_id")),
        "source_document_id": _clean(row.get("source_document_id")),
        "document_type": _clean(row.get("document_type")),
        "title": _clean(row.get("title")),
        "year": _parse_int(row.get("year")),
        "number": _clean(row.get("number")),
        "document_date": _parse_date(row.get("date")),
        "language": _clean(row.get("language")),
        "source_url": _clean(row.get("source_url")),
        "download_url": _clean(row.get("download_url")),
        "local_path": _clean(row.get("local_path")),
        "file_hash": _clean(row.get("file_hash")),
        "acquisition_status": _clean(row.get("acquisition_status")) or "metadata_extracted",
        "extraction_status": _clean(row.get("extraction_status")) or "not_started",
        "ocr_required": _parse_bool(row.get("ocr_required")),
        "text_quality_score": _parse_float(row.get("text_quality_score")),
        "legal_status": _clean(row.get("legal_status")),
        "missing_reason": _clean(row.get("missing_reason")),
        "next_action": _clean(row.get("next_action")),
        "last_checked": _parse_datetime(row.get("last_checked")),
        "notes": _clean(row.get("notes")),
    }


def validate_document_registry(rows: list[dict[str, str]]) -> RegistryValidationReport:
    issues: list[RegistryValidationIssue] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    downloaded_count = 0
    missing_count = 0
    for index, raw_row in enumerate(rows, start=2):
        row = normalize_document_row(raw_row)
        for field in REQUIRED_DOCUMENT_FIELDS:
            if not row.get(field):
                issues.append(RegistryValidationIssue(index, field, "required field is empty"))
        document_id = str(row.get("document_id") or "")
        if document_id:
            if document_id in seen:
                duplicates.add(document_id)
            seen.add(document_id)
        acquisition_status = str(row["acquisition_status"])
        if acquisition_status in DOWNLOADED_ACQUISITION_STATUSES:
            downloaded_count += 1
        if acquisition_status in MISSING_ACQUISITION_STATUSES:
            missing_count += 1
            if not row.get("next_action"):
                issues.append(RegistryValidationIssue(index, "next_action", "missing document rows require next_action"))
    return RegistryValidationReport(
        row_count=len(rows),
        duplicate_document_ids=tuple(sorted(duplicates)),
        issues=tuple(issues),
        downloaded_count=downloaded_count,
        missing_count=missing_count,
    )


def document_ingestion_status(acquisition_status: str, extraction_status: str) -> str:
    if acquisition_status == "downloaded" and extraction_status in {"text_extracted", "package_extracted", "extracted"}:
        return "extracted"
    if acquisition_status == "downloaded":
        return "downloaded"
    if acquisition_status in MISSING_ACQUISITION_STATUSES:
        return "skipped"
    if "failed" in acquisition_status or "failed" in extraction_status:
        return "failed"
    return "queued"


def document_stage(acquisition_status: str, extraction_status: str) -> str:
    if extraction_status and extraction_status != "not_started":
        return "text_extraction"
    if acquisition_status == "downloaded":
        return "download"
    return "registry"


def build_registry_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_missing_source_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "external_missing_id": _clean(row.get("missing_id")),
        "category": _clean(row.get("data_category")) or "Unclassified",
        "title": _clean(row.get("missing_description")) or _clean(row.get("data_category")) or "Missing source",
        "year": _parse_int(row.get("year")),
        "reason": _clean(row.get("missing_description")) or "Missing source requires verification.",
        "next_action": _clean(row.get("next_action")) or "Locate and verify source.",
        "priority": _priority_from_importance(row.get("legal_importance")),
        "status": _clean(row.get("status")) or "open",
        "expected_coverage": _clean(row.get("expected_coverage")),
        "known_available_coverage": _clean(row.get("known_available_coverage")),
        "legal_importance": _clean(row.get("legal_importance")),
        "risk_if_missing": _clean(row.get("risk_if_missing")),
        "probable_source": _clean(row.get("probable_source")),
        "owner": _clean(row.get("owner")),
        "last_checked": _parse_datetime(row.get("last_checked")),
        "notes": _clean(row.get("notes")),
    }


def _priority_from_importance(value: str | None) -> str:
    normalized = _clean(value).lower()
    if normalized in {"critical", "high", "normal", "low"}:
        return normalized
    return "normal"


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _parse_int(value: str | None) -> int | None:
    value = _clean(value)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    value = _clean(value)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_bool(value: str | None) -> bool | None:
    value = _clean(value).lower()
    if not value:
        return None
    if value in {"true", "1", "yes", "y"}:
        return True
    if value in {"false", "0", "no", "n"}:
        return False
    return None


def _parse_date(value: str | None) -> date | None:
    value = _clean(value)
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    value = _clean(value)
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
