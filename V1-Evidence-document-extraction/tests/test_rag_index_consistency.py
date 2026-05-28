from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_consistency_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_rag_index_consistency.py"
    spec = importlib.util.spec_from_file_location("check_rag_index_consistency", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalize_psycopg_dsn_accepts_sqlalchemy_driver_form():
    module = load_consistency_module()

    assert module.normalize_psycopg_dsn("postgresql+psycopg://user:pass@localhost/db") == (
        "postgresql://user:pass@localhost/db"
    )


def test_parse_args_defaults_to_local_service_names():
    module = load_consistency_module()

    args = module.parse_args([])

    assert args.opensearch_index == "sl_legal_retrieval_chunks"
    assert args.qdrant_collection == "sl_legal_retrieval_chunks"
    assert args.embedding_provider == "sentence-transformers"
    assert args.embedding_model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert args.embedding_dimensions == 384
