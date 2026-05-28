from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_two_stage_case_reports.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_two_stage_case_reports", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sample_report():
    return {
        "fixture_path": "rag/evals/two_stage_tuned_cases.json",
        "cases": [
            {
                "case_id": "sample_case",
                "title": "Sample & Case",
                "case_facts": "A union alleges refusal to bargain.",
                "query": "Industrial Disputes collective bargaining",
                "status": "pass",
                "elapsed_ms": 123,
                "stage1_candidate_count": 10,
                "metrics": {
                    "expected_count": 2,
                    "stage1_expected_recall": 1.0,
                    "top_k_expected_recall": 1.0,
                },
                "failures": [],
                "top_documents": [
                    {
                        "rank": 1,
                        "relevance_score": 99.5,
                        "document_id": "doc_1",
                        "title": "Industrial Disputes Act & Rules",
                        "document_type": "Act",
                        "year": 1950,
                        "source_id": "PARL_ACTS",
                        "summary_search_excerpt": "summary extract",
                        "best_full_text_chunk": {
                            "page_start": 1,
                            "page_end": 2,
                            "excerpt": "No employer shall refuse collective bargaining.",
                        },
                    }
                ],
            }
        ],
    }


def test_latex_escape_handles_special_characters():
    module = load_module()

    assert module.latex_escape("A&B_50%") == r"A\&B\_50\%"


def test_metadata_cleaner_removes_mojibake_dash_without_llm():
    module = load_module()

    assert module.clean_metadata_text('Local Government ??" Pradeshiya Sabha Act.No.15') == "Local Government - Pradeshiya Sabha Act No.15"


def test_render_case_tex_uses_tcolorbox_and_color_categories():
    module = load_module()
    report = sample_report()

    tex = module.render_case_tex(report, report["cases"][0], top_documents=1, chunk_chars=500)

    assert r"\usepackage[most]{tcolorbox}" in tex
    assert "Case" in tex
    assert "Evidence Documents" in tex
    assert "Final relevance score" in tex
    assert "ActFrame" in tex
    assert r"Industrial Disputes Act \& Rules" in tex
    assert "Summary" in tex
    assert "Document ID:" not in tex
    assert r"\textbf{Year:} 1950\\" in tex
    assert r"\textbf{Final relevance score:} 99.50\\" in tex
    assert r"\textbf{Status:} pass\\" in tex
    assert r"\textbf{Elapsed:} 123 ms\\" in tex
    assert r"\textbf{Report:} \texttt{rag/evals/two\_stage\_tuned\_cases.json}" in tex
    assert r"\textbf{Status:} pass \quad" not in tex
    assert "Relevant chunk summaries" in tex
    assert "Evidence chunks combined" in tex


def test_generate_reports_writes_manifest_ready_tex(tmp_path):
    module = load_module()
    report = sample_report()

    generated = module.generate_reports(
        report,
        tmp_path,
        top_documents=1,
        chunk_chars=500,
        compile_pdf=False,
        compiler="auto",
    )

    assert len(generated) == 1
    tex_path = Path(generated[0]["tex_path"])
    assert tex_path.exists()
    assert tex_path.read_text(encoding="utf-8").startswith(r"\documentclass")


def test_generate_reports_can_filter_case_ids(tmp_path):
    module = load_module()
    report = sample_report()
    report["cases"].append({**report["cases"][0], "case_id": "other_case"})

    generated = module.generate_reports(
        report,
        tmp_path,
        top_documents=1,
        chunk_chars=500,
        compile_pdf=False,
        compiler="auto",
        case_ids={"other_case"},
    )

    assert [item["case_id"] for item in generated] == ["other_case"]


def test_render_case_tex_can_clean_evidence_before_latex():
    module = load_module()

    class Cleaner(module.EvidenceTextCleaner):
        def clean(self, text, *, context):
            return "cleaned evidence text"

    report = sample_report()
    tex = module.render_case_tex(report, report["cases"][0], top_documents=1, chunk_chars=500, cleaner=Cleaner())

    assert "cleaned evidence text" in tex
    assert "No employer shall refuse collective bargaining" not in tex


def test_conservative_cleaner_removes_garbled_parallel_gazette_header():
    module = load_module()
    cleaner = module.ConservativeEvidenceTextCleaner()

    cleaned = cleaner.clean(
        "IV ^w& jeks fldgi - Y%S ,xld garbage PART IV (A) - GAZETTE EXTRAORDINARY OF THE DEMOCRATIC SOCIALIST REPUBLIC OF SRI LANKA - 09.05.2018",
        context="test",
    )

    assert cleaned.startswith("PART IV (A)")
    assert "fldgi" not in cleaned


def test_conservative_cleaner_repairs_common_ocr_typos():
    module = load_module()
    cleaner = module.ConservativeEvidenceTextCleaner()

    cleaned = cleaner.clean("calendar yer approved annyally by the Pradeshiya Sabhaand officer", context="test")

    assert "calendar year" in cleaned
    assert "approved annually" in cleaned
    assert "Pradeshiya Sabha and" in cleaned


def test_summary_abstract_is_not_rendered_by_default():
    module = load_module()
    report = sample_report()

    tex = module.render_case_tex(report, report["cases"][0], top_documents=1, chunk_chars=500)

    assert "Summary-search abstract" not in tex
    assert "summary extract" not in tex


def test_document_excerpt_prefers_complete_chunk_text_over_short_excerpt():
    module = load_module()
    document = {
        "summary_search_excerpt": "summary text",
        "best_full_text_chunk": {
            "excerpt": "short excerpt...",
            "chunk_text": "complete retrieved chunk text",
        },
    }

    assert (
        module.document_excerpt(document, chunk_chars=500, cleaner=module.EvidenceTextCleaner(), context="test")
        == "complete retrieved chunk text"
    )


def test_render_case_tex_merges_duplicate_document_chunks_into_one_box():
    module = load_module()
    report = sample_report()
    case = report["cases"][0]
    case["top_documents"] = [
        {
            "rank": 1,
            "relevance_score": 95.0,
            "document_id": "doc_1",
            "title": "Industrial Disputes Act",
            "document_type": "Act",
            "year": 1950,
            "source_id": "PARL_ACTS",
            "best_full_text_chunk": {
                "chunk_id": "chunk_1",
                "page_start": 1,
                "page_end": 1,
                "chunk_score": 1.0,
                "chunk_text": "An employer shall not refuse collective bargaining with a qualifying trade union.",
            },
        },
        {
            "rank": 2,
            "relevance_score": 88.0,
            "document_id": "doc_1",
            "title": "Industrial Disputes Act",
            "document_type": "Act",
            "year": 1950,
            "source_id": "PARL_ACTS",
            "best_full_text_chunk": {
                "chunk_id": "chunk_2",
                "page_start": 2,
                "page_end": 3,
                "chunk_score": 0.8,
                "chunk_text": "The tribunal may consider an industrial dispute involving bargaining.",
            },
        },
    ]

    tex = module.render_case_tex(report, case, top_documents=25, chunk_chars=500)

    assert tex.count(r"\begin{tcolorbox}") == 3
    assert "Evidence chunks combined:} 2" in tex
    assert "Chunk 1 -- pages 1-1 -- score 1.000" in tex
    assert "Chunk 2 -- pages 2-3 -- score 0.800" in tex


def test_distinct_case_documents_scans_beyond_first_twenty_five_for_unique_docs():
    module = load_module()
    case = {"top_documents": []}
    for index in range(40):
        case["top_documents"].append(
            {
                "rank": index + 1,
                "relevance_score": 100 - index,
                "document_id": "dup" if index < 10 else f"doc_{index}",
                "title": "Duplicate" if index < 10 else f"Document {index}",
                "document_type": "Act",
                "source_id": "PARL_ACTS",
                "best_full_text_chunk": {"chunk_id": f"chunk_{index}", "excerpt": f"chunk {index}"},
            }
        )

    distinct = module.distinct_case_documents(case, top_documents=25)

    assert len(distinct) == 25
    assert distinct[0]["document_id"] == "dup"
    assert len(distinct[0]["evidence_chunks"]) == 10
    assert [doc["rank"] for doc in distinct] == list(range(1, 26))
