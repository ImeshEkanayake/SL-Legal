#!/usr/bin/env python3
"""Run the corpus full-text extraction and OCR gate in resumable batches."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.full_text_readiness import (  # noqa: E402
    build_full_text_readiness_report,
    read_csv_rows,
    read_ocr_rows,
    write_report_json,
)


MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
OCR_REGISTER_PATH = PROJECT_ROOT / "data" / "manifests" / "ocr_results_register.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "manifests" / "full_text_readiness_report.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run extraction, OCR, registry import, and page loading.")
    parser.add_argument("--source-id", action="append", help="Limit processing to one or more source IDs.")
    parser.add_argument("--document-id", action="append", help="Limit extraction to one or more document IDs.")
    parser.add_argument("--document-id-file", action="append", help="Read document IDs from newline-delimited files.")
    parser.add_argument("--year", action="append", help="Limit extraction to one or more years.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum documents per extraction/OCR phase. 0 means no cap.")
    parser.add_argument("--ocr-workers", type=int, default=2)
    parser.add_argument("--ocr-batch-size", type=int, default=20)
    parser.add_argument("--ocr-dpi", type=int, default=250)
    parser.add_argument("--ocr-language", default="eng")
    parser.add_argument("--ocr-document-timeout", type=int, default=600)
    parser.add_argument("--minimum-text-quality", type=float, default=0.60)
    parser.add_argument("--skip-text-extraction", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--force-ocr", action="store_true", help="Retry OCR rows already present in the OCR register.")
    parser.add_argument("--skip-postgres-load", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
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


def command_with_filters(command: list[str], args: argparse.Namespace) -> list[str]:
    for source_id in args.source_id or []:
        command.extend(["--source-id", source_id])
    for document_id in sorted(args.document_ids_filter):
        command.extend(["--document-id", document_id])
    for year in args.year or []:
        command.extend(["--year", year])
    if args.limit:
        command.extend(["--limit", str(args.limit)])
    return command


def require_runtime() -> dict[str, str | bool]:
    return {"python": sys.executable, "tesseract": shutil.which("tesseract") or ""}


def require_execution_runtime(args: argparse.Namespace) -> None:
    if not args.skip_text_extraction:
        import pypdf  # noqa: F401
        import pypdfium2  # noqa: F401

    if not args.skip_ocr:
        import pypdfium2  # noqa: F401
        import PIL.Image  # noqa: F401

        if not shutil.which("tesseract"):
            raise SystemExit("tesseract is required for OCR and was not found on PATH")

    if not args.skip_postgres_load:
        import psycopg  # noqa: F401
        import sqlalchemy  # noqa: F401


def build_report(args: argparse.Namespace):
    manifest_rows = read_csv_rows(MANIFEST_PATH)
    ocr_rows = read_ocr_rows(OCR_REGISTER_PATH)
    report = build_full_text_readiness_report(
        manifest_rows,
        ocr_rows,
        minimum_text_quality=args.minimum_text_quality,
    )
    report_path = Path(args.report_path)
    if not report_path.is_absolute():
        report_path = PROJECT_ROOT / report_path
    write_report_json(report_path, report)
    return report, report_path


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


def build_commands(args: argparse.Namespace) -> list[list[str]]:
    commands: list[list[str]] = []
    if not args.skip_text_extraction:
        extraction = [
            sys.executable,
            "scripts/extract_downloaded_pdf_text.py",
            "--progress-every",
            "100",
            "--checkpoint-every",
            "100",
        ]
        commands.append(command_with_filters(extraction, args))

    if not args.skip_ocr:
        ocr = [
            sys.executable,
            "scripts/ocr_text_empty_pdfs.py",
            "--workers",
            str(args.ocr_workers),
            "--batch-size",
            str(args.ocr_batch_size),
            "--dpi",
            str(args.ocr_dpi),
            "--language",
            args.ocr_language,
            "--document-timeout",
            str(args.ocr_document_timeout),
        ]
        if args.force_ocr:
            ocr.append("--force")
        for source_id in args.source_id or []:
            ocr.extend(["--source-id", source_id])
        for document_id in sorted(args.document_ids_filter):
            ocr.extend(["--document-id", document_id])
        for year in args.year or []:
            ocr.extend(["--year", year])
        if args.limit:
            ocr.extend(["--limit", str(args.limit)])
        commands.append(ocr)

    if not args.skip_postgres_load:
        registry_import = [sys.executable, "scripts/import_data_registry.py"]
        for source_id in args.source_id or []:
            registry_import.extend(["--filter-source-id", source_id])
        for document_id in sorted(args.document_ids_filter):
            registry_import.extend(["--document-id", document_id])
        for year in args.year or []:
            registry_import.extend(["--year", year])
        if args.limit:
            registry_import.extend(["--limit", str(args.limit)])

        page_load = [sys.executable, "scripts/load_pages_postgres.py"]
        for source_id in args.source_id or []:
            page_load.extend(["--source-id", source_id])
        for document_id in sorted(args.document_ids_filter):
            page_load.extend(["--document-id", document_id])
        if args.limit:
            page_load.extend(["--limit-documents", str(args.limit)])

        commands.extend(
            [
                registry_import,
                page_load,
            ]
        )
    return commands


def print_summary(label: str, report, report_path: Path) -> None:
    payload = report.to_json()
    print(
        json.dumps(
            {
                "label": label,
                "report_path": str(report_path.relative_to(PROJECT_ROOT)),
                "downloaded_documents": payload["downloaded_documents"],
                "downloaded_pdfs": payload["downloaded_pdfs"],
                "full_text_ready_documents": payload["full_text_ready_documents"],
                "remaining_for_full_text": payload["remaining_for_full_text"],
                "extraction_pending_documents": payload["extraction_pending_documents"],
                "ocr_pending_documents": payload["ocr_pending_documents"],
                "extraction_failed_documents": payload["extraction_failed_documents"],
                "full_text_ready_ratio": payload["full_text_ready_ratio"],
            },
            indent=2,
        )
    )


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    require_runtime()

    before, report_path = build_report(args)
    print_summary("before", before, report_path)
    commands = build_commands(args)

    if not args.execute:
        print(json.dumps({"dry_run": True, "planned_commands": commands}, indent=2))
        return 0

    require_execution_runtime(args)
    for command in commands:
        run_command(command)
    after, report_path = build_report(args)
    print_summary("after", after, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
