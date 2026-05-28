from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag import two_stage_retrieval as retrieval


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_two_stage_recall_precision_checks.py"
PRODUCTION_MODULE_PATH = PROJECT_ROOT / "rag" / "sl_legal_rag" / "two_stage_retrieval.py"
TUNED_FIXTURE_PATH = PROJECT_ROOT / "rag" / "evals" / "two_stage_tuned_cases.json"
BLIND_FIXTURE_PATH = PROJECT_ROOT / "rag" / "evals" / "two_stage_blind_cases.json"


def load_module():
    spec = importlib.util.spec_from_file_location("run_two_stage_recall_precision_checks", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_query_tokenization_and_tsquery_are_broad_but_safe():
    tokens = retrieval.tokenize("Sri Lanka Industrial Disputes Act, collective bargaining and workmen transfers")

    assert "sri" not in tokens
    assert "lanka" not in tokens
    assert "industrial" in tokens
    assert "bargaining" in tokens
    assert retrieval.to_prefix_tsquery(tokens) == "industrial:* | disputes:* | collective:* | bargaining:* | workmen:* | transfers:*"


def test_excerpt_around_terms_returns_abstract_like_context():
    text = "Opening words. " + ("background " * 80) + "The employer refused collective bargaining with the trade union. " + ("tail " * 80)

    excerpt = retrieval.excerpt_around_terms(text, ["collective", "bargaining"], radius=60)

    assert "collective bargaining" in excerpt
    assert excerpt.startswith("...")
    assert excerpt.endswith("...")


def test_metric_summary_tracks_stage1_and_top_k_recall_separately():
    runner = load_module()
    stage1 = [
        retrieval.SummaryCandidate("doc_a", "tv_a", "A", "Act", "SRC", 2000, "English", None, None, "summary", 1, 1, 1, 1, 1),
        retrieval.SummaryCandidate("doc_b", "tv_b", "B", "Act", "SRC", 2001, "English", None, None, "summary", 1, 1, 1, 1, 2),
    ]
    final = [
        retrieval.RankedDocument(
            candidate=stage1[1],
            metrics=retrieval.FullTextMetrics("tv_b", 100, 25, "source", "English", None, "not_applicable", [], 1, 1, 1, 2, 0),
            evidence_chunks=[],
            term_coverage=1,
            raw_score=1,
            relevance_score=100,
            final_rank=1,
        )
    ]

    summary = runner.metric_summary({"doc_a", "doc_b", "doc_c"}, stage1, final, top_k=25)

    assert summary["stage1_expected_recall"] == 0.666667
    assert summary["top_k_expected_recall"] == 0.333333
    assert summary["missing_from_stage1"] == ["doc_c"]
    assert summary["missing_from_top_k"] == ["doc_a", "doc_c"]


def test_title_hint_multiplier_boosts_named_instrument_families():
    query = "Intellectual Property trademark infringement registration"

    assert retrieval.title_hint_multiplier(query, "Intellectual Property (Amendment)") > 1
    assert retrieval.title_hint_multiplier(query, "Penal Code") < 1


def test_serialized_ranked_document_keeps_all_evidence_chunks():
    candidate = retrieval.SummaryCandidate(
        "doc_a",
        "tv_a",
        "Industrial Disputes Act",
        "Act",
        "PARL_ACTS",
        1950,
        "English",
        None,
        None,
        "summary collective bargaining",
        1,
        1,
        1,
        1,
        1,
    )
    ranked = retrieval.RankedDocument(
        candidate=candidate,
        metrics=retrieval.FullTextMetrics("tv_a", 1000, 250, "source", "English", None, "not_applicable", [], 1, 1, 1, 2, 0),
        evidence_chunks=[
            retrieval.EvidenceChunk("chunk_a", 1, 1, "refusal to bargain evidence", 1, 0.5, 1.5),
            retrieval.EvidenceChunk("chunk_b", 2, 3, "trade union evidence", 0.8, 0.4, 1.2),
        ],
        term_coverage=1,
        raw_score=1,
        relevance_score=100,
        final_rank=1,
    )

    payload = retrieval.serialize_ranked_document(ranked, query="collective bargaining", tokens=["bargaining", "union"])

    assert [chunk["chunk_id"] for chunk in payload["evidence_chunks"]] == ["chunk_a", "chunk_b"]
    assert payload["best_full_text_chunk"]["chunk_id"] == "chunk_a"
    assert payload["scoring_breakdown"]["evidence_chunk_count"] == 2


def test_production_module_has_no_fixture_expected_documents():
    source = PRODUCTION_MODULE_PATH.read_text(encoding="utf-8")

    assert "SAMPLE_CASES" not in source
    assert "ExpectedSelector" not in source
    assert "gov_extra_gazette_1862_08_e_b5e7eebf3c" not in source
    assert "parl_act_1951_014_g5327" not in source


def test_eval_fixtures_are_external_and_loadable():
    runner = load_module()

    tuned = runner.load_fixture(TUNED_FIXTURE_PATH)
    blind = runner.load_fixture(BLIND_FIXTURE_PATH)

    assert len(tuned) == 10
    assert len(blind) == 10
    assert all(case.expected_selectors for case in tuned)
    assert all(case.expected_selectors for case in blind)
