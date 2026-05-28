#!/usr/bin/env python3
"""Extract text from downloaded corpus PDFs and update the document manifest.

Use the bundled Codex Python runtime for this script because it includes pypdf:

  /Users/imeshekanayake/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/extract_downloaded_pdf_text.py
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPS = PROJECT_ROOT / ".codex_deps" / "ocr"
if LOCAL_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DEPS))

from pypdf import PdfReader

try:
    import pypdfium2 as pdfium
except Exception:  # pragma: no cover - fallback is optional.
    pdfium = None


MANIFEST_PATH = PROJECT_ROOT / "data" / "manifests" / "document_manifest.csv"
TEXT_DIR = PROJECT_ROOT / "data" / "extracted" / "text"
RUN_LOG_PATH = PROJECT_ROOT / "data" / "manifests" / "extraction_run_log.csv"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_corpus_module():
    script = PROJECT_ROOT / "scripts" / "extract_legal_corpus.py"
    spec = importlib.util.spec_from_file_location("extract_legal_corpus", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_run_log(run: dict[str, str]) -> None:
    rows = read_csv(RUN_LOG_PATH)
    fields = list(rows[0].keys()) if rows else [
        "run_id",
        "source_id",
        "run_type",
        "started_at",
        "ended_at",
        "documents_found",
        "documents_downloaded",
        "errors",
        "new_missing_items",
        "notes",
    ]
    rows.append(run)
    write_csv(RUN_LOG_PATH, fields, rows)


def page_text_quality(text: str, page_count: int) -> tuple[str, bool]:
    chars = len(text.strip())
    if chars == 0:
        return "0.00", True
    if page_count <= 0:
        return "0.50", False
    chars_per_page = chars / page_count
    if chars_per_page < 100:
        return "0.25", True
    if chars_per_page < 500:
        return "0.60", False
    return "0.90", False


def clean_text(text: str) -> str:
    return text.encode("utf-8", "replace").decode("utf-8")


def extract_with_pypdf(pdf_path: Path) -> list[dict[str, str]]:
    reader = PdfReader(str(pdf_path), strict=False)
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = clean_text(page.extract_text() or "")
        except Exception as exc:
            text = ""
            pages.append({"page": index, "text": "", "error": str(exc)})
            continue
        pages.append({"page": index, "text": text, "error": ""})
    return pages


def extract_with_pdfium(pdf_path: Path) -> list[dict[str, str]]:
    if pdfium is None:
        raise RuntimeError("pypdfium2 fallback is unavailable")
    pdf = pdfium.PdfDocument(str(pdf_path))
    pages = []
    try:
        for index in range(len(pdf)):
            page_number = index + 1
            page = None
            textpage = None
            try:
                page = pdf[index]
                textpage = page.get_textpage()
                text = clean_text(textpage.get_text_range() or "")
                pages.append({"page": page_number, "text": text, "error": ""})
            except Exception as exc:
                pages.append({"page": page_number, "text": "", "error": str(exc)})
            finally:
                if textpage is not None:
                    textpage.close()
                if page is not None:
                    page.close()
    finally:
        pdf.close()
    return pages


def extract_pdf(row: dict[str, str]) -> tuple[str, dict[str, object]]:
    local_path = row.get("local_path", "")
    if not local_path:
        raise ValueError("manifest row has no local_path")
    pdf_path = PROJECT_ROOT / local_path
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))

    extractor = "pypdf"
    try:
        pages = extract_with_pypdf(pdf_path)
    except Exception:
        extractor = "pypdfium2"
        pages = extract_with_pdfium(pdf_path)

    combined = "\n\n".join(page["text"] for page in pages).strip()
    document_id = row["document_id"]
    text_path = TEXT_DIR / f"{document_id}.txt"
    pages_path = TEXT_DIR / f"{document_id}.pages.jsonl"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(combined, encoding="utf-8")
    with pages_path.open("w", encoding="utf-8") as handle:
        for page in pages:
            handle.write(json.dumps(page, ensure_ascii=False) + "\n")

    quality, needs_ocr = page_text_quality(combined, len(pages))
    metadata = {
        "page_count": len(pages),
        "char_count": len(combined),
        "text_path": str(text_path.relative_to(PROJECT_ROOT)),
        "pages_path": str(pages_path.relative_to(PROJECT_ROOT)),
        "quality": quality,
        "needs_ocr": needs_ocr,
        "extractor": extractor,
    }
    return "text_extracted" if combined else "text_empty_needs_ocr", metadata


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract text from downloaded PDFs.")
    parser.add_argument("--document-id", action="append", help="Limit extraction to one or more document IDs.")
    parser.add_argument("--source-id", action="append", help="Limit extraction to one or more source IDs.")
    parser.add_argument("--year", action="append", help="Limit extraction to one or more years.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum PDFs to process. 0 means no limit.")
    parser.add_argument("--force", action="store_true", help="Re-extract rows already marked as text extracted.")
    parser.add_argument("--progress-every", type=int, default=50, help="Print progress every N processed PDFs. 0 disables progress.")
    parser.add_argument("--checkpoint-every", type=int, default=50, help="Write manifest progress every N processed PDFs. 0 writes only at end.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = utc_now()
    corpus = load_corpus_module()
    rows = read_csv(MANIFEST_PATH)
    document_ids = set(args.document_id or [])
    source_ids = set(args.source_id or [])
    years = set(args.year or [])
    processed = 0
    errors: list[str] = []

    for row in rows:
        if row.get("acquisition_status") != "downloaded":
            continue
        if document_ids and row.get("document_id") not in document_ids:
            continue
        if source_ids and row.get("source_id") not in source_ids:
            continue
        if years and row.get("year") not in years:
            continue
        if not args.force and row.get("extraction_status") in {"text_extracted", "text_empty_needs_ocr"}:
            continue
        if args.limit and processed >= args.limit:
            break
        try:
            status, metadata = extract_pdf(row)
            row["extraction_status"] = status
            row["ocr_required"] = "true" if metadata["needs_ocr"] else "false"
            row["text_quality_score"] = metadata["quality"]
            row["last_checked"] = utc_now()
            note = (
                f"text_path={metadata['text_path']}; pages_path={metadata['pages_path']}; "
                f"pages={metadata['page_count']}; chars={metadata['char_count']}; "
                f"extractor={metadata['extractor']}"
            )
            prior = row.get("notes", "")
            row["notes"] = f"{prior}; {note}" if prior else note
            processed += 1
            if args.progress_every and (
                processed == 1 or processed % args.progress_every == 0
            ):
                print(
                    f"extracted {processed} latest={row.get('document_id')} status={status} "
                    f"pages={metadata['page_count']} chars={metadata['char_count']}",
                    file=sys.stderr,
                    flush=True,
                )
            if args.checkpoint_every and processed % args.checkpoint_every == 0:
                write_csv(MANIFEST_PATH, corpus.DOCUMENT_MANIFEST_FIELDS, rows)
        except Exception as exc:
            row["extraction_status"] = "text_extraction_failed"
            row["ocr_required"] = "unknown"
            row["last_checked"] = utc_now()
            errors.append(f"{row.get('document_id')}: {exc}")
            if args.checkpoint_every and (processed + len(errors)) % args.checkpoint_every == 0:
                write_csv(MANIFEST_PATH, corpus.DOCUMENT_MANIFEST_FIELDS, rows)

    write_csv(MANIFEST_PATH, corpus.DOCUMENT_MANIFEST_FIELDS, rows)
    corpus.refresh_acts_missing_register()
    corpus.build_corpus_index(
        {
            "pdf_text_extraction": {
                "started_at": started,
                "ended_at": utc_now(),
                "document_ids": sorted(document_ids),
                "source_ids": sorted(source_ids),
                "years": sorted(years),
                "documents_processed": processed,
                "errors": errors,
            }
        }
    )
    append_run_log(
        {
            "run_id": "run_" + started.replace(":", "").replace("-", "").replace("+", "z") + "_pdf_text",
            "source_id": "DOWNLOADED_PDFS",
            "run_type": "pdf_text_extraction",
            "started_at": started,
            "ended_at": utc_now(),
            "documents_found": str(processed),
            "documents_downloaded": "0",
            "errors": json.dumps(errors, ensure_ascii=False),
            "new_missing_items": "",
            "notes": "Extracted text from downloaded PDFs and updated document manifest.",
        }
    )
    print(json.dumps({"processed": processed, "errors": errors}, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
