#!/usr/bin/env python3
"""Build and sync RAG chunks for a controlled document batch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNK_DIR = PROJECT_ROOT / "data" / "indexes"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--document-id", action="append", help="Only index these document IDs.")
    parser.add_argument("--document-id-file", action="append", help="Read document IDs from newline-delimited files.")
    parser.add_argument("--source-id", action="append", help="Only index these source IDs.")
    parser.add_argument("--document-type", action="append", help="Only index these document types.")
    parser.add_argument("--include-gazettes", action="store_true")
    parser.add_argument(
        "--include-translation-text-versions",
        action="store_true",
        help="When building from Postgres, also index English translation fallback text versions.",
    )
    parser.add_argument(
        "--only-translation-text-versions",
        action="store_true",
        help="When building from Postgres, index only English translation fallback text versions.",
    )
    parser.add_argument(
        "--replace-text-version-scope",
        action="store_true",
        help="Delete existing chunks for input text_version_ids from each index before loading replacements.",
    )
    parser.add_argument(
        "--from-postgres",
        action="store_true",
        help="Build chunks from documents/pages already in Postgres instead of the raw document manifest.",
    )
    parser.add_argument("--output", help="Chunk JSONL output path.")
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--skip-opensearch", action="store_true")
    parser.add_argument("--skip-qdrant", action="store_true")
    parser.add_argument("--embedding-provider", default="sentence-transformers")
    parser.add_argument("--embedding-model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--embedding-dimensions", type=int, default=384)
    parser.add_argument("--qdrant-batch-size", type=int, default=32)
    args = parser.parse_args(argv)
    args.document_ids_filter = load_document_ids(args)
    return args


def load_document_ids(args: argparse.Namespace) -> set[str]:
    document_ids = set(args.document_id or [])
    for file_name in args.document_id_file or []:
        path = Path(file_name)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        for line in path.read_text(encoding="utf-8").splitlines():
            normalized = line.strip()
            if normalized and not normalized.startswith("#"):
                document_ids.add(normalized)
    return document_ids


def resolved_output_path(args: argparse.Namespace) -> Path:
    if args.output:
        path = Path(args.output)
        return path if path.is_absolute() else PROJECT_ROOT / path
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_CHUNK_DIR / f"rag_index_wave_{stamp}.jsonl"


def with_common_filters(command: list[str], args: argparse.Namespace) -> list[str]:
    for document_id in sorted(args.document_ids_filter):
        command.extend(["--document-id", document_id])
    for source_id in args.source_id or []:
        command.extend(["--source-id", source_id])
    for document_type in args.document_type or []:
        command.extend(["--document-type", document_type])
    if args.include_gazettes:
        command.append("--include-gazettes")
    if args.include_translation_text_versions:
        command.append("--include-translation-text-versions")
    if args.only_translation_text_versions:
        command.append("--only-translation-text-versions")
    return command


def build_commands(args: argparse.Namespace, chunks_path: Path) -> list[list[str]]:
    builder_script = "scripts/build_rag_chunks_from_postgres.py" if args.from_postgres else "scripts/build_rag_chunks.py"
    commands = [
        with_common_filters(
            [sys.executable, builder_script, "--output", str(chunks_path.relative_to(PROJECT_ROOT))],
            args,
        )
    ]
    if not args.skip_postgres:
        command = [sys.executable, "scripts/load_rag_chunks_postgres.py", "--mode", "docker", "--chunks", str(chunks_path.relative_to(PROJECT_ROOT))]
        if args.replace_text_version_scope:
            command.append("--replace-text-version-scope")
        commands.append(command)
    if not args.skip_opensearch:
        command = [sys.executable, "scripts/load_rag_chunks_opensearch.py", "--chunks", str(chunks_path.relative_to(PROJECT_ROOT))]
        if args.replace_text_version_scope:
            command.append("--replace-text-version-scope")
        commands.append(command)
    if not args.skip_qdrant:
        command = [
                sys.executable,
                "scripts/load_rag_chunks_qdrant.py",
                "--chunks",
                str(chunks_path.relative_to(PROJECT_ROOT)),
                "--provider",
                args.embedding_provider,
                "--model",
                args.embedding_model,
                "--dimensions",
                str(args.embedding_dimensions),
                "--batch-size",
                str(args.qdrant_batch_size),
            ]
        if args.replace_text_version_scope:
            command.append("--replace-text-version-scope")
        commands.append(command)
    commands.append([sys.executable, "scripts/check_rag_index_consistency.py"])
    return commands


def run_command(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = "rag" if not env.get("PYTHONPATH") else f"rag{os.pathsep}{env['PYTHONPATH']}"
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    chunks_path = resolved_output_path(args)
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    commands = build_commands(args, chunks_path)
    if not args.execute:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "chunks_path": str(chunks_path.relative_to(PROJECT_ROOT)),
                    "document_ids": sorted(args.document_ids_filter),
                    "planned_commands": commands,
                },
                indent=2,
            )
        )
        return 0
    for command in commands:
        run_command(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
