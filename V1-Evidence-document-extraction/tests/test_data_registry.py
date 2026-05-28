from __future__ import annotations

from sl_legal_rag.data_registry import (
    document_ingestion_status,
    document_stage,
    normalize_document_row,
    normalize_missing_source_row,
    validate_document_registry,
)
from scripts.import_data_registry import filter_document_rows, parse_args


def test_document_registry_validation_detects_duplicates_and_missing_next_action():
    rows = [
        {
            "document_id": "doc_1",
            "source_id": "PARL_ACTS",
            "document_type": "Act",
            "title": "Act One",
            "acquisition_status": "downloaded",
        },
        {
            "document_id": "doc_1",
            "source_id": "PARL_ACTS",
            "document_type": "Act",
            "title": "Act One Duplicate",
            "acquisition_status": "metadata_extracted_pdf_not_found",
        },
    ]

    report = validate_document_registry(rows)

    assert not report.valid
    assert report.duplicate_document_ids == ("doc_1",)
    assert any(issue.field == "next_action" for issue in report.issues)
    assert report.downloaded_count == 1
    assert report.missing_count == 1


def test_document_registry_normalization_and_status_mapping():
    row = normalize_document_row(
        {
            "document_id": " doc_2 ",
            "source_id": "GOV_GAZETTES",
            "document_type": "Gazette",
            "title": " Gazette Notice ",
            "year": "2026",
            "date": "2026-05-24",
            "acquisition_status": "downloaded",
            "extraction_status": "text_extracted",
            "ocr_required": "false",
            "text_quality_score": "0.97",
        }
    )

    assert row["document_id"] == "doc_2"
    assert row["year"] == 2026
    assert row["document_date"].isoformat() == "2026-05-24"
    assert row["ocr_required"] is False
    assert row["text_quality_score"] == 0.97
    assert document_ingestion_status(row["acquisition_status"], row["extraction_status"]) == "extracted"
    assert document_stage(row["acquisition_status"], row["extraction_status"]) == "text_extraction"


def test_missing_source_registry_normalization_preserves_risk_and_owner():
    row = normalize_missing_source_row(
        {
            "missing_id": "M001",
            "data_category": "Historical Court Material",
            "missing_description": "Pre-online Supreme Court judgments are incomplete.",
            "legal_importance": "critical",
            "risk_if_missing": "Binding authority may be missed.",
            "probable_source": "Supreme Court; Law reports",
            "next_action": "Acquire archival scans.",
            "owner": "Corpus lead",
            "status": "open",
            "last_checked": "2026-05-24T12:00:00+00:00",
        }
    )

    assert row["external_missing_id"] == "M001"
    assert row["category"] == "Historical Court Material"
    assert row["priority"] == "critical"
    assert row["owner"] == "Corpus lead"
    assert row["last_checked"].isoformat() == "2026-05-24T12:00:00+00:00"


def test_registry_import_filters_manifest_rows_by_source_document_and_year():
    rows = [
        {"document_id": "doc_1", "source_id": "SC_OFFICIAL", "year": "2024"},
        {"document_id": "doc_2", "source_id": "SC_OFFICIAL", "year": "2023"},
        {"document_id": "doc_3", "source_id": "CA_OFFICIAL", "year": "2024"},
    ]

    args = parse_args(["--filter-source-id", "SC_OFFICIAL", "--year", "2024"])

    assert filter_document_rows(rows, args) == [rows[0]]

    args = parse_args(["--document-id", "doc_3"])

    assert filter_document_rows(rows, args) == [rows[2]]


def test_registry_import_reads_document_id_file(tmp_path):
    document_id_file = tmp_path / "ids.txt"
    document_id_file.write_text("doc_2\n", encoding="utf-8")
    rows = [
        {"document_id": "doc_1", "source_id": "SC_OFFICIAL", "year": "2024"},
        {"document_id": "doc_2", "source_id": "SC_OFFICIAL", "year": "2023"},
    ]

    args = parse_args(["--document-id-file", str(document_id_file)])

    assert filter_document_rows(rows, args) == [rows[1]]
