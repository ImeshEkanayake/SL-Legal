from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_pipeline_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_rag_index_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_rag_index_pipeline", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rag_index_pipeline_builds_end_to_end_commands(tmp_path):
    module = load_pipeline_module()
    document_id_file = tmp_path / "ids.txt"
    document_id_file.write_text("doc_1\n", encoding="utf-8")
    args = module.parse_args(["--document-id-file", str(document_id_file), "--output", "data/indexes/test_chunks.jsonl"])
    commands = module.build_commands(args, module.PROJECT_ROOT / "data" / "indexes" / "test_chunks.jsonl")

    flattened = [" ".join(command) for command in commands]

    assert any("build_rag_chunks.py" in command and "--document-id doc_1" in command for command in flattened)
    assert any("load_rag_chunks_postgres.py" in command for command in flattened)
    assert any("load_rag_chunks_opensearch.py" in command for command in flattened)
    assert any("load_rag_chunks_qdrant.py" in command for command in flattened)
    assert any("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" in command for command in flattened)
    assert any("check_rag_index_consistency.py" in command for command in flattened)


def test_rag_index_pipeline_can_build_from_postgres(tmp_path):
    module = load_pipeline_module()
    document_id_file = tmp_path / "ids.txt"
    document_id_file.write_text("doc_case_file\n", encoding="utf-8")

    args = module.parse_args(
        [
            "--from-postgres",
            "--include-translation-text-versions",
            "--only-translation-text-versions",
            "--replace-text-version-scope",
            "--document-id-file",
            str(document_id_file),
            "--output",
            "data/indexes/test_chunks.jsonl",
        ]
    )
    commands = module.build_commands(args, module.PROJECT_ROOT / "data" / "indexes" / "test_chunks.jsonl")

    assert "scripts/build_rag_chunks_from_postgres.py" in commands[0]
    assert "--document-id" in commands[0]
    assert "doc_case_file" in commands[0]
    assert "--include-translation-text-versions" in commands[0]
    assert "--only-translation-text-versions" in commands[0]
    assert "--replace-text-version-scope" in commands[1]
    assert "--replace-text-version-scope" in commands[2]
    assert "--replace-text-version-scope" in commands[3]
