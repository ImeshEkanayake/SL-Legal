#!/usr/bin/env python3
"""Load RAG chunks into PostgreSQL.

Run after:
  docker compose -f docker-compose.rag.yml up -d rag-postgres
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data" / "indexes" / "rag_chunks.jsonl"
DEFAULT_DSN = "postgresql://sl_legal:sl_legal_dev@localhost:5433/sl_legal_assist"
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.rag.yml"


def load_chunks(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load RAG chunks into PostgreSQL.")
    parser.add_argument("--chunks", default=str(DEFAULT_CHUNKS_PATH))
    parser.add_argument("--dsn", default=os.getenv("SL_LEGAL_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--replace-text-version-scope",
        action="store_true",
        help="Delete existing retrieval_chunks for text_version_ids present in the input before loading replacements.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "docker", "psycopg"],
        default="auto",
        help="Use psycopg if installed, or the Postgres container via docker.",
    )
    return parser.parse_args(argv)


def collect_text_version_ids(path: Path) -> list[str]:
    text_version_ids: set[str] = set()
    for chunk in load_chunks(path):
        text_version_id = str(chunk.get("text_version_id") or "").strip()
        if text_version_id:
            text_version_ids.add(text_version_id)
    return sorted(text_version_ids)


def docker_compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def load_with_psycopg(args: argparse.Namespace, chunks_path: Path) -> dict[str, int]:
    import psycopg

    documents_seen: set[str] = set()
    chunks_loaded = 0

    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            if args.replace_text_version_scope:
                text_version_ids = collect_text_version_ids(chunks_path)
                if text_version_ids:
                    cur.execute("DELETE FROM retrieval_chunks WHERE text_version_id = ANY(%s)", (text_version_ids,))
                    conn.commit()
            for chunk in load_chunks(chunks_path):
                if chunk["document_id"] not in documents_seen:
                    cur.execute(
                        """
                        INSERT INTO documents (
                            document_id, source_id, document_type, title, year, number,
                            document_date, language, source_url, local_path,
                            acquisition_status, extraction_status, legal_status
                        )
                        VALUES (
                            %(document_id)s, %(source_id)s, %(document_type)s, %(title)s,
                            %(year)s, %(number)s, NULLIF(%(date)s, '')::date, %(language)s,
                            %(source_url)s, %(local_path)s, 'downloaded',
                            %(extraction_status)s, %(legal_status)s
                        )
                        ON CONFLICT (document_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            year = EXCLUDED.year,
                            source_url = EXCLUDED.source_url,
                            local_path = EXCLUDED.local_path,
                            updated_at = now()
                        """,
                        {
                            **chunk,
                            "extraction_status": chunk.get("metadata", {}).get("extraction_status", "text_extracted"),
                            "legal_status": chunk.get("metadata", {}).get("legal_status", "to_verify"),
                        },
                    )
                    documents_seen.add(chunk["document_id"])

                cur.execute(
                    """
                    INSERT INTO retrieval_chunks (
                        chunk_id, document_id, source_id, document_type, title, year,
                        authority_level, page_start, page_end, chunk_index, chunk_text,
                        token_estimate, language, citation, source_url, local_path,
                        text_hash, quality_flags, metadata, text_version_id, text_origin,
                        source_language, translated_from_language, translation_review_status
                    )
                    VALUES (
                        %(chunk_id)s, %(document_id)s, %(source_id)s, %(document_type)s,
                        %(title)s, %(year)s, %(authority_level)s, %(page_start)s,
                        %(page_end)s, %(chunk_index)s, %(chunk_text)s, %(token_estimate)s,
                        %(language)s, %(citation)s, %(source_url)s, %(local_path)s,
                        %(text_hash)s, %(quality_flags)s, %(metadata)s::jsonb,
                        NULLIF(%(text_version_id)s, ''), %(text_origin)s,
                        NULLIF(%(source_language)s, ''),
                        NULLIF(%(translated_from_language)s, ''),
                        NULLIF(%(translation_review_status)s, '')
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        chunk_text = EXCLUDED.chunk_text,
                        token_estimate = EXCLUDED.token_estimate,
                        citation = EXCLUDED.citation,
                        quality_flags = EXCLUDED.quality_flags,
                        metadata = EXCLUDED.metadata,
                        text_version_id = EXCLUDED.text_version_id,
                        text_origin = EXCLUDED.text_origin,
                        source_language = EXCLUDED.source_language,
                        translated_from_language = EXCLUDED.translated_from_language,
                        translation_review_status = EXCLUDED.translation_review_status
                    """,
                    {
                        **chunk,
                        "quality_flags": chunk.get("quality_flags", []),
                        "metadata": json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                        "text_version_id": chunk.get("text_version_id", ""),
                        "text_origin": chunk.get("text_origin", "source"),
                        "source_language": chunk.get("source_language", chunk.get("language", "")),
                        "translated_from_language": chunk.get("translated_from_language", ""),
                        "translation_review_status": chunk.get("translation_review_status", ""),
                    },
                )
                chunks_loaded += 1
                if chunks_loaded % args.batch_size == 0:
                    conn.commit()
            conn.commit()

    return {"documents_loaded": len(documents_seen), "chunks_loaded": chunks_loaded}


def load_with_docker(args: argparse.Namespace, chunks_path: Path) -> dict[str, int]:
    if not chunks_path.exists():
        raise FileNotFoundError(chunks_path)
    container_json = "/tmp/sl_legal_rag_chunks.csv"
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", suffix=".csv", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
        writer = csv.writer(temp_file)
        with chunks_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    writer.writerow([line.strip()])
        temp_file.flush()
        temp_path.chmod(0o644)
    try:
        docker_compose("cp", str(temp_path), f"rag-postgres:{container_json}")
    finally:
        temp_path.unlink(missing_ok=True)

    replace_scope_sql = (
        """
DELETE FROM retrieval_chunks
WHERE text_version_id IN (
    SELECT DISTINCT NULLIF(payload->>'text_version_id', '')
    FROM tmp_rag_chunks
    WHERE NULLIF(payload->>'text_version_id', '') IS NOT NULL
);
"""
        if args.replace_text_version_scope
        else ""
    )

    sql = f"""
CREATE TEMP TABLE tmp_rag_chunks (payload jsonb);
COPY tmp_rag_chunks(payload) FROM '{container_json}' WITH (FORMAT csv);

{replace_scope_sql}

INSERT INTO documents (
    document_id, source_id, source_document_id, document_type, title, year, number,
    document_date, language, source_url, local_path, acquisition_status,
    extraction_status, legal_status
)
SELECT DISTINCT ON (payload->>'document_id')
    payload->>'document_id',
    payload->>'source_id',
    payload->'metadata'->>'source_document_id',
    payload->>'document_type',
    payload->>'title',
    NULLIF(payload->>'year', '')::integer,
    payload->>'number',
    NULLIF(payload->>'date', '')::date,
    payload->>'language',
    payload->>'source_url',
    payload->>'local_path',
    'downloaded',
    COALESCE(payload->'metadata'->>'extraction_status', 'text_extracted'),
    COALESCE(payload->'metadata'->>'legal_status', 'to_verify')
FROM tmp_rag_chunks
ON CONFLICT (document_id) DO UPDATE SET
    source_id = EXCLUDED.source_id,
    document_type = EXCLUDED.document_type,
    title = EXCLUDED.title,
    year = EXCLUDED.year,
    number = EXCLUDED.number,
    document_date = EXCLUDED.document_date,
    language = EXCLUDED.language,
    source_url = EXCLUDED.source_url,
    local_path = EXCLUDED.local_path,
    extraction_status = EXCLUDED.extraction_status,
    legal_status = EXCLUDED.legal_status,
    updated_at = now();

INSERT INTO retrieval_chunks (
    chunk_id, document_id, source_id, document_type, title, year,
    authority_level, page_start, page_end, chunk_index, chunk_text,
    token_estimate, language, citation, source_url, local_path,
    text_hash, quality_flags, metadata, text_version_id, text_origin,
    source_language, translated_from_language, translation_review_status
)
SELECT
    payload->>'chunk_id',
    payload->>'document_id',
    payload->>'source_id',
    payload->>'document_type',
    payload->>'title',
    NULLIF(payload->>'year', '')::integer,
    (payload->>'authority_level')::integer,
    NULLIF(payload->>'page_start', '')::integer,
    NULLIF(payload->>'page_end', '')::integer,
    (payload->>'chunk_index')::integer,
    payload->>'chunk_text',
    (payload->>'token_estimate')::integer,
    payload->>'language',
    payload->>'citation',
    payload->>'source_url',
    payload->>'local_path',
    payload->>'text_hash',
    COALESCE(
        ARRAY(SELECT jsonb_array_elements_text(payload->'quality_flags')),
        '{{}}'::text[]
    ),
    COALESCE(payload->'metadata', '{{}}'::jsonb),
    NULLIF(payload->>'text_version_id', ''),
    COALESCE(NULLIF(payload->>'text_origin', ''), 'source'),
    NULLIF(COALESCE(payload->>'source_language', payload->>'language'), ''),
    NULLIF(payload->>'translated_from_language', ''),
    NULLIF(payload->>'translation_review_status', '')
FROM tmp_rag_chunks
ON CONFLICT (chunk_id) DO UPDATE SET
    chunk_text = EXCLUDED.chunk_text,
    token_estimate = EXCLUDED.token_estimate,
    citation = EXCLUDED.citation,
    quality_flags = EXCLUDED.quality_flags,
    metadata = EXCLUDED.metadata,
    text_version_id = EXCLUDED.text_version_id,
    text_origin = EXCLUDED.text_origin,
    source_language = EXCLUDED.source_language,
    translated_from_language = EXCLUDED.translated_from_language,
    translation_review_status = EXCLUDED.translation_review_status;

SELECT
    (SELECT count(DISTINCT payload->>'document_id') FROM tmp_rag_chunks)::text
    || '|' ||
    (SELECT count(*) FROM tmp_rag_chunks)::text;
"""
    result = docker_compose(
        "exec",
        "-T",
        "rag-postgres",
        "psql",
        "-U",
        "sl_legal",
        "-d",
        "sl_legal_assist",
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-c",
        sql,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout)
    summary = result.stdout.strip().splitlines()[-1]
    documents_loaded, chunks_loaded = summary.split("|", 1)
    return {"documents_loaded": int(documents_loaded), "chunks_loaded": int(chunks_loaded)}


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    chunks_path = Path(args.chunks)
    if not chunks_path.is_absolute():
        chunks_path = PROJECT_ROOT / chunks_path

    if args.mode == "docker":
        result = load_with_docker(args, chunks_path)
    else:
        try:
            if args.mode == "psycopg":
                result = load_with_psycopg(args, chunks_path)
            else:
                try:
                    result = load_with_psycopg(args, chunks_path)
                except ImportError:
                    result = load_with_docker(args, chunks_path)
        except ImportError as exc:
            raise SystemExit("Missing dependency: install requirements-rag.txt or use --mode docker.") from exc

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
