from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest


def load_sync_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "sync_corpus_assets_to_object_storage.py"
    spec = importlib.util.spec_from_file_location("sync_corpus_assets_to_object_storage", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_storage_key_is_stable_and_scoped_by_document():
    module = load_sync_module()
    config = module.StorageConfig(
        provider="minio",
        endpoint_url="http://localhost:9000",
        bucket="sl-legal-corpus",
        region="us-east-1",
        access_key="local",
        secret_key="local",
        prefix="corpus",
    )
    candidate = module.AssetCandidate(
        document_id="parl_act_1950_043_g5240",
        source_id="PARL_ACTS",
        source_document_id="G5240",
        document_type="Act",
        title="Industrial Disputes Act",
        year=1950,
        number="43",
        document_date=None,
        language="English",
        source_url="https://example.test/source",
        download_url="https://example.test/file.pdf",
        local_path="data/raw/file.pdf",
        file_hash="",
        acquisition_status="downloaded",
        extraction_status="text_extracted",
        text_quality_score=0.9,
        legal_status="to_verify",
        notes="",
    )

    key = module.storage_key(config, candidate, "a" * 64, ".PDF", kind="original")

    assert key == "corpus/original/parl_acts/parl_act_1950_043_g5240/" + ("a" * 64) + ".pdf"


def test_translated_text_storage_key_is_separate_from_source_extraction():
    module = load_sync_module()
    config = module.StorageConfig(
        provider="minio",
        endpoint_url="http://localhost:9000",
        bucket="sl-legal-corpus",
        region="us-east-1",
        access_key="local",
        secret_key="local",
        prefix="corpus",
    )
    candidate = module.AssetCandidate(
        document_id="gov_gazette_si_001",
        source_id="GOV_GAZETTES",
        source_document_id="2026-01-01:I:S",
        document_type="Gazette",
        title="Sinhala Gazette",
        year=2026,
        number="",
        document_date=None,
        language="Sinhala",
        source_url="https://example.test/source",
        download_url="https://example.test/file.pdf",
        local_path="data/raw/file.pdf",
        file_hash="",
        acquisition_status="downloaded",
        extraction_status="text_extracted",
        text_quality_score=0.8,
        legal_status="to_verify",
        notes="",
    )

    key = module.translated_text_storage_key(config, candidate, "English", "b" * 64)

    assert key == "corpus/translations/gov_gazettes/gov_gazette_si_001/english/translated_text_" + ("b" * 64) + ".txt"


def test_sha256_file_hashes_bytes(tmp_path):
    module = load_sync_module()
    path = tmp_path / "fixture.txt"
    path.write_bytes(b"legal text")

    digest = module.local_file_digest(path)

    assert digest.sha256 == hashlib.sha256(b"legal text").hexdigest()
    assert digest.byte_size == len(b"legal text")
    assert digest.content_type == "text/plain"


def test_translation_text_version_requires_explicit_provenance():
    module = load_sync_module()
    candidate = module.AssetCandidate(
        document_id="doc_translation",
        source_id="GOV_GAZETTES",
        source_document_id="2026-01-01:I:S",
        document_type="Gazette",
        title="Sinhala Gazette",
        year=2026,
        number="",
        document_date=None,
        language="Sinhala",
        source_url="",
        download_url="",
        local_path="data/raw/file.pdf",
        file_hash="",
        acquisition_status="downloaded",
        extraction_status="text_extracted",
        text_quality_score=0.8,
        legal_status="to_verify",
        notes="",
    )
    text_version = module.TextVersion(
        full_text="Translated fallback",
        page_count=1,
        char_count=19,
        text_hash="d" * 64,
        extraction_method="machine_translation",
        ocr_confidence_mean=None,
        ocr_confidence_band=None,
        quality_flags=["translated_text_fallback"],
        text_origin="translation",
    )

    with pytest.raises(ValueError, match="translation text versions require"):
        module.upsert_text_version(
            object(),
            candidate=candidate,
            source_asset_id="asset_source",
            text_asset_id="asset_translation",
            text_version=text_version,
            ingestion_run_id=None,
        )


def test_best_page_key_prefers_non_empty_longer_text():
    module = load_sync_module()

    empty = {"text": "", "extraction_method": "ocr", "ocr_confidence": 99}
    useful = {"text": "substantial page text", "extraction_method": "text_layer", "ocr_confidence": None}

    assert module.best_page_key(useful) > module.best_page_key(empty)


def test_sync_summary_tracks_preview_bytes_and_errors():
    module = load_sync_module()
    summary = module.SyncSummary(candidate_count=2)

    summary.add({"document_id": "a", "status": "synced", "byte_size": 12})
    summary.add({"document_id": "b", "status": "hash_mismatch", "byte_size": 5})

    assert summary.processed_count == 2
    assert summary.error_count == 1
    assert summary.total_bytes == 17
    assert summary.status_counts == {"synced": 1, "hash_mismatch": 1}
    assert [result["document_id"] for result in summary.results_preview] == ["a", "b"]


def test_default_ingestion_run_id_is_scoped_by_source_and_scope():
    module = load_sync_module()
    args = module.parse_args(["--scope", "manifest", "--source-id", "PARL_ACTS"])

    run_id = module.default_ingestion_run_id(args)

    assert run_id.startswith("object_asset_sync_manifest_parl_acts_")
