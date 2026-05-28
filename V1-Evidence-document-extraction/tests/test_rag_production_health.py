from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_health_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_rag_production_health.py"
    spec = importlib.util.spec_from_file_location("check_rag_production_health", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalize_psycopg_dsn_accepts_sqlalchemy_driver_form():
    module = load_health_module()

    assert module.normalize_psycopg_dsn("postgresql+psycopg://user:pass@localhost/db") == (
        "postgresql://user:pass@localhost/db"
    )


def test_evaluate_zero_counts_reports_only_nonzero_failures():
    module = load_health_module()

    failures = module.evaluate_zero_counts({"documents_without_chunks": 0, "chunks_with_empty_text": 2})

    assert [failure.check for failure in failures] == ["chunks_with_empty_text"]
    assert failures[0].expected == 0


def test_evaluate_minimums_reports_low_counts():
    module = load_health_module()
    args = module.parse_args(["--min-documents", "3", "--min-pages", "10", "--min-chunks", "5"])

    failures = module.evaluate_minimums({"documents": 2, "pages": 10, "retrieval_chunks": 4}, args)

    assert [failure.check for failure in failures] == ["minimum_documents", "minimum_retrieval_chunks"]
